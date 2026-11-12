"""Versioned store for trained outlook models.

    models/
      registry.json                 {"active": "<version>", "history": [...]}
      outlook/<version>/model.joblib  fitted sklearn pipeline (trained on all complete targets)
      outlook/<version>/model_card.json  config, features, data window, metrics, provenance

Training happens in `sentinel/train.py` (locally, in Docker or in Google Colab). A model only
becomes *active* if it passes the promotion gate; `outlook.run()` then uses its config.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
from pathlib import Path

from . import config as C

MODELS_DIR = Path(os.environ.get("SENTINEL_MODELS_DIR", C.ROOT / "models"))


def models_dir() -> Path:
    return MODELS_DIR


def _registry_path() -> Path:
    return models_dir() / "registry.json"


def read_registry() -> dict:
    p = _registry_path()
    return json.loads(p.read_text()) if p.exists() else {"active": None, "history": []}


def _write_registry(reg: dict) -> None:
    models_dir().mkdir(parents=True, exist_ok=True)
    _registry_path().write_text(json.dumps(reg, indent=2))


def new_version() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("v%Y%m%d-%H%M%S")


def git_sha() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=C.ROOT, capture_output=True,
                              text=True, timeout=5).stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def save(model, card: dict, version: str | None = None) -> Path:
    import joblib
    version = version or card.get("version") or new_version()
    d = models_dir() / "outlook" / version
    d.mkdir(parents=True, exist_ok=True)
    card = {**card, "version": version, "saved_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "git_sha": card.get("git_sha") or git_sha()}
    joblib.dump(model, d / "model.joblib")
    (d / "model_card.json").write_text(json.dumps(card, indent=2, default=str))
    reg = read_registry()
    reg["history"] = [h for h in reg["history"] if h["version"] != version] + [
        {"version": version, "saved_utc": card["saved_utc"], "test_bss": card.get("test", {}).get("bss_vs_climatology"),
         "promoted": False}]
    _write_registry(reg)
    return d


def load_card(version: str) -> dict | None:
    p = models_dir() / "outlook" / version / "model_card.json"
    return json.loads(p.read_text()) if p.exists() else None


def load_model(version: str):
    import joblib
    return joblib.load(models_dir() / "outlook" / version / "model.joblib")


def active_card() -> dict | None:
    v = read_registry().get("active")
    return load_card(v) if v else None


def promotion_decision(candidate: dict, active: dict | None, ece_tolerance: float = 0.02) -> tuple[bool, str]:
    """Gate: promote only if the candidate is demonstrably useful.

    1. Its test BSS vs climatology has a 90% CI lower bound above 0 (real skill), or
    2. there is an active model and the candidate has a lower test Brier score without
       being worse calibrated (ECE within tolerance).
    """
    t = candidate.get("test", {})
    lo = (t.get("bss_90ci") or [float("nan")])[0]
    if lo is not None and lo == lo and lo > 0:
        return True, f"BSS 90% CI lower bound {lo:.3f} > 0"
    if active:
        a = active.get("test", {})
        if t.get("brier", 1) < a.get("brier", 1) and t.get("ece", 1) <= a.get("ece", 1) + ece_tolerance:
            return True, f"Brier {t['brier']:.4f} < active {a['brier']:.4f} with ECE {t['ece']:.3f}"
        return False, "does not beat the active model on Brier with equal-or-better calibration"
    return False, "no demonstrable skill over climatology (BSS CI includes 0); keeping inline default"


def promote(version: str, reason: str) -> None:
    reg = read_registry()
    reg["active"] = version
    for h in reg["history"]:
        if h["version"] == version:
            h["promoted"], h["reason"] = True, reason
    _write_registry(reg)


def deactivate() -> None:
    reg = read_registry()
    reg["active"] = None
    _write_registry(reg)


def import_bundle(path: Path) -> str:
    """Copy a model folder (or .zip of it) exported from Colab into models/outlook/<version>/."""
    import shutil
    import tempfile
    import zipfile
    path = Path(path)
    tmp = None
    if path.suffix == ".zip":
        tmp = Path(tempfile.mkdtemp())
        with zipfile.ZipFile(path) as z:
            z.extractall(tmp)
        cards = list(tmp.rglob("model_card.json"))
        if len(cards) != 1:
            raise ValueError("zip must contain exactly one model_card.json")
        path = cards[0].parent
    card = json.loads((path / "model_card.json").read_text())
    dest = models_dir() / "outlook" / card["version"]
    dest.mkdir(parents=True, exist_ok=True)
    for f in ("model.joblib", "model_card.json"):
        shutil.copy2(path / f, dest / f)
    reg = read_registry()
    if not any(h["version"] == card["version"] for h in reg["history"]):
        reg["history"].append({"version": card["version"], "saved_utc": card.get("saved_utc"),
                               "test_bss": card.get("test", {}).get("bss_vs_climatology"), "promoted": False})
        _write_registry(reg)
    if tmp:
        shutil.rmtree(tmp, ignore_errors=True)
    return card["version"]


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Outlook model registry: list | import <zip|dir> | promote <version> [--force] | deactivate")
    ap.add_argument("cmd", choices=["list", "import", "promote", "deactivate"])
    ap.add_argument("arg", nargs="?")
    ap.add_argument("--force", action="store_true", help="promote even if the gate fails")
    a = ap.parse_args()
    if a.cmd == "list":
        reg = read_registry()
        print("active:", reg["active"])
        for h in reg["history"]:
            print(f"  {h['version']}  test BSS={h.get('test_bss')}  promoted={h.get('promoted')}")
    elif a.cmd == "import":
        print("imported", import_bundle(Path(a.arg)))
    elif a.cmd == "promote":
        card = load_card(a.arg)
        if card is None:
            raise SystemExit(f"unknown version {a.arg}")
        ok, why = promotion_decision(card, active_card())
        if not ok and not a.force:
            raise SystemExit(f"gate failed: {why} (use --force to override)")
        promote(a.arg, why if ok else f"forced: {why}")
        print("active ->", a.arg, f"({why})")
    else:
        deactivate()
        print("no active model; pipeline uses inline selection")
