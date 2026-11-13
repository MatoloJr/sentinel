"""Independent check of our rainfall drought indicator against NDMA's official county drought phases.

NDMA (National Drought Management Authority) publishes a monthly Drought Early Warning bulletin per ASAL county
that classifies the county as Normal / Alert / Alarm / Emergency / Recovery. Only bulletins that were actually
downloaded and read are used: a month whose bulletin is not listed, cannot be downloaded or whose phase cannot be
read from the PDF text is stored as "not available". Nothing is guessed.

    node scripts/ndma_list_bulletins.js data/reference/ndma_bulletin_index.csv   # 1. list bulletins (needs Playwright)
    python scripts/ndma_compare.py extract                                       # 2. download + read phases
    python scripts/ndma_compare.py                                               # 3. compare -> outputs/ndma_agreement.csv

Mapping (from sentinel/playbook.json drought level descriptions): Watch ~ Alert, Warning ~ Alarm,
Emergency ~ Emergency, Normal ~ Normal. NDMA 'Recovery' has no rainfall equivalent and is left out of the
agreement numbers (counted separately), as are our 'Dry season (not assessed)' months.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import csv
import io
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
REF = ROOT / "data" / "reference"
INDEX_CSV = REF / "ndma_bulletin_index.csv"
PHASES_CSV = REF / "ndma_phases.csv"
OUT_CSV = ROOT / "outputs" / "ndma_agreement.csv"
OUT_JSON = ROOT / "outputs" / "ndma_agreement.json"
DROUGHT = ROOT / "outputs" / "drought.parquet"
PLAYBOOK = ROOT / "sentinel" / "playbook.json"

COUNTIES = ["Turkana", "Marsabit", "Mandera", "Wajir", "Garissa", "Tana River", "Makueni", "Kilifi", "Kwale", "Lamu"]
PHASES = ["Normal", "Alert", "Alarm", "Emergency", "Recovery"]
NA = "not available"
PHASE_COLS = ["county", "month", "ndma_phase", "bulletin_url", "accessed_utc", "evidence"]
WINDOW = 3  # months either side when matching an NDMA escalation in time

_P = "|".join(PHASES)
# 1) the 'County' row of the EW phase classification table, e.g. "County Alarm Worsening"
COUNTY_ROW = re.compile(rf"^\s*county\s*[:\-]?\s*({_P})\b", re.I | re.M)
# 2) a header such as "Drought Phase:ALERT-WORSENING" or "DROUGHT EW PHASE: ALARM"
HEADER = re.compile(rf"drought\s+(?:ew\s+|early\s+warning\s+)?phase\s*(?:classification)?\s*[:\-]?\s*({_P})\b", re.I)


# ------------------------------------------------------------------ reading bulletins
def parse_phase(text: str) -> tuple[str, str]:
    """(phase, evidence) from the text of a bulletin's first pages; (NA, reason) when it cannot be read."""
    if not text or not text.strip():
        return NA, "no extractable text (scanned image?)"
    rows = {m.group(1).title() for m in COUNTY_ROW.finditer(text)}
    if len(rows) == 1:
        m = COUNTY_ROW.search(text)
        return rows.pop(), _snip(text, m)
    if len(rows) > 1:
        return NA, f"ambiguous County rows: {sorted(rows)}"
    heads = {m.group(1).title() for m in HEADER.finditer(text)}
    if len(heads) == 1:
        m = HEADER.search(text)
        return heads.pop(), _snip(text, m)
    if len(heads) > 1:
        return NA, f"ambiguous phase headers: {sorted(heads)}"
    return NA, "phase classification not found in text"


def _snip(text: str, m: re.Match) -> str:
    end = text.find("\n", m.end())
    line = text[text.rfind("\n", 0, m.start()) + 1: end if end >= 0 else len(text)]
    return re.sub(r"\s+", " ", line).strip()[:120]


def _pdf_text(data: bytes, pages: int = 2) -> str:
    import pypdf
    r = pypdf.PdfReader(io.BytesIO(data))
    return "\n".join((r.pages[i].extract_text() or "") for i in range(min(pages, len(r.pages))))


def _download(url: str, tries: int = 3) -> bytes:
    import requests
    last = None
    for t in range(tries):
        try:
            r = requests.get(url, timeout=180)
            r.raise_for_status()
            if not r.content.startswith(b"%PDF"):
                raise ValueError(f"not a PDF ({r.headers.get('content-type')})")
            return r.content
        except Exception as e:  # noqa: BLE001 - recorded as the reason
            last = e
            time.sleep(3 * (t + 1))
    raise RuntimeError(str(last))


def _read_one(row: dict) -> dict:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        phase, ev = parse_phase(_pdf_text(_download(row["pdf_url"])))
    except Exception as e:  # noqa: BLE001
        phase, ev = NA, f"download/read failed: {str(e)[:100]}"
    return {"county": row["county"], "month": row["month"], "ndma_phase": phase,
            "bulletin_url": row["pdf_url"], "accessed_utc": now, "evidence": ev}


def extract(index_csv: Path = INDEX_CSV, phases_csv: Path = PHASES_CSV, workers: int = 4,
            first: str = "2021-01", retry_na: bool = False) -> pd.DataFrame:
    """Download and read every listed bulletin not read yet; fill unlisted county-months with 'not available'."""
    idx = pd.read_csv(index_csv, dtype=str)
    idx = idx[idx["county"].isin(COUNTIES)].drop_duplicates("doc_id")
    have = pd.read_csv(phases_csv, dtype=str).fillna("") if phases_csv.exists() else pd.DataFrame(columns=PHASE_COLS)
    have = have[have["bulletin_url"] != ""]  # unlisted placeholders are rebuilt below
    if retry_na:
        have = have[have["ndma_phase"] != NA]
    done = set(zip(have["county"], have["month"]))
    todo = [r for r in idx.to_dict("records") if (r["county"], r["month"]) not in done]
    print(f"{len(idx)} bulletins listed, {len(done)} already read, {len(todo)} to read")
    rows = have.to_dict("records")
    with cf.ThreadPoolExecutor(workers) as ex:
        for i, res in enumerate(ex.map(_read_one, todo), 1):
            rows.append(res)
            print(f"[{i}/{len(todo)}] {res['county']} {res['month']}: {res['ndma_phase']} | {res['evidence'][:70]}", flush=True)
            if i % 20 == 0:
                _write_phases(rows, idx, phases_csv, first)
    return _write_phases(rows, idx, phases_csv, first)


def _merge_duplicates(df: pd.DataFrame) -> pd.DataFrame:
    """More than one bulletin listed for a county-month: keep it only if every copy gives the same phase."""
    out = []
    for _, g in df.groupby(["county", "month"], sort=False):
        if len(g) == 1:
            out.append(g.iloc[0].to_dict())
            continue
        read = g[g["ndma_phase"] != NA]
        r = (read if len(read) else g).iloc[0].to_dict()
        if read["ndma_phase"].nunique() > 1:
            r.update(ndma_phase=NA, evidence="conflicting bulletins: " + "; ".join(f"{a} ({b[:40]})" for a, b in zip(read.ndma_phase, read.bulletin_url)))
        elif len(read):
            r["bulletin_url"] = " ".join(read["bulletin_url"])
        out.append(r)
    return pd.DataFrame(out, columns=PHASE_COLS)


def _write_phases(rows: list[dict], idx: pd.DataFrame, phases_csv: Path, first: str) -> pd.DataFrame:
    df = _merge_duplicates(pd.DataFrame(rows, columns=PHASE_COLS))
    last = max(idx["month"]) if len(idx) else first
    months = pd.period_range(first, last, freq="M").strftime("%Y-%m")
    grid = pd.MultiIndex.from_product([COUNTIES, months], names=["county", "month"]).to_frame(index=False)
    df = grid.merge(df, on=["county", "month"], how="left")
    miss = df["ndma_phase"].isna()
    df.loc[miss, "ndma_phase"] = NA
    df.loc[miss, "evidence"] = "no bulletin listed on NDMA KnowledgeWeb for this county-month"
    df = df.fillna("").sort_values(["county", "month"])
    phases_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(phases_csv, index=False, quoting=csv.QUOTE_MINIMAL)
    return df


# ------------------------------------------------------------------ comparison
def ndma_mapping(playbook: Path = PLAYBOOK) -> dict[str, str]:
    """Our level -> NDMA phase, read from the playbook's drought level descriptions ("comparable to NDMA 'X'")."""
    pb = json.loads(playbook.read_text(encoding="utf-8"))
    levels = pb["levels"]["drought"]
    m = {"Normal": "Normal"}
    for lvl, text in levels.items():
        hit = re.search(r"NDMA '(\w+)'", text)
        if hit:
            m[lvl] = hit.group(1)
    return m


def compare(phases: pd.DataFrame, drought: pd.DataFrame, mapping: dict[str, str]) -> tuple[pd.DataFrame, dict]:
    """Per-county agreement between NDMA phases and our drought level for the same month."""
    rank = {ph: i for i, ph in enumerate(["Normal", "Alert", "Alarm", "Emergency"])}
    ours_rank = {lvl: rank[ph] for lvl, ph in mapping.items() if ph in rank}
    p = phases[phases["ndma_phase"].isin(PHASES)].copy()
    p["m"] = pd.PeriodIndex(p["month"], freq="M")
    d = drought[["county", "date", "level"]].copy()
    d["m"] = pd.to_datetime(d["date"]).dt.to_period("M")
    x = p.merge(d[["county", "m", "level"]], on=["county", "m"], how="left")
    x["n"] = x["ndma_phase"].map(rank)          # NaN for Recovery
    x["o"] = x["level"].map(ours_rank)          # NaN for dry season / missing
    rows = []
    for county, g in x.groupby("county"):
        rows.append(_county_row(county, g, phases[phases["county"] == county], d[d["county"] == county], ours_rank))
    out = pd.DataFrame(rows)
    tot = _county_row("ALL", x, phases, d, ours_rank)
    out = pd.concat([out, pd.DataFrame([tot])], ignore_index=True)
    overall = {k: (None if isinstance(v, float) and np.isnan(v) else v) for k, v in tot.items()}
    overall["mapping"] = mapping
    return out, overall


def _pct(a, b):
    return round(100 * a / b, 1) if b else np.nan


def _county_row(county, g, ph, d, ours_rank) -> dict:
    c = g.dropna(subset=["n", "o"])
    n, o = c["n"].to_numpy(), c["o"].to_numpy()
    timing = _escalations(g, d, ours_rank)
    ndma_alert = n >= 1
    ours_watch = o >= 1
    return {
        "county": county,
        "bulletins_read": int(len(g)),
        "not_available": int((ph["ndma_phase"] == NA).sum()),
        "recovery_excluded": int((g["ndma_phase"] == "Recovery").sum()),
        "dry_season_excluded": int((g["level"] == "Dry season (not assessed)").sum()),
        "months_compared": int(len(c)),
        "exact_agreement_pct": _pct((n == o).sum(), len(c)),
        "within_one_level_pct": _pct((abs(n - o) <= 1).sum(), len(c)),
        "always_normal_baseline_pct": _pct((n == 0).sum(), len(c)),
        "ndma_alert_plus_months": int(ndma_alert.sum()),
        "we_watch_plus_when_ndma_alert_plus_pct": _pct((ndma_alert & ours_watch).sum(), ndma_alert.sum()),
        "we_watch_plus_when_ndma_normal_pct": _pct((~ndma_alert & ours_watch).sum(), (~ndma_alert).sum()),
        "we_higher_months": int((o > n).sum()),
        "we_lower_months": int((o < n).sum()),
        **timing,
    }


def _escalations(g, d, ours_rank) -> dict:
    """At each NDMA escalation (phase rises vs the previous month), when did our indicator first reach the same
    level within +/- WINDOW months? earlier = before NDMA, later = after, not_matched = not within the window."""
    res = {"ndma_escalations": 0, "we_earlier": 0, "same_month": 0, "we_later": 0, "not_matched": 0}
    leads = []
    for county, gc in g.groupby("county"):
        s = gc.set_index("m")["n"].sort_index()
        dc = d[d["county"] == county].set_index("m")["level"].map(ours_rank)
        for m, lvl in s.items():
            prev = s.get(m - 1)
            if not (lvl >= 1 and prev is not None and not np.isnan(prev) and lvl > prev):
                continue
            res["ndma_escalations"] += 1
            hit = [k for k in range(-WINDOW, WINDOW + 1) if dc.get(m + k, np.nan) >= lvl]
            if not hit:
                res["not_matched"] += 1
                continue
            k = min(hit)  # earliest month in the window at which we reached NDMA's level
            leads.append(-k)
            res["we_earlier" if k < 0 else "same_month" if k == 0 else "we_later"] += 1
    res["median_lead_months"] = float(np.median(leads)) if leads else np.nan
    return res


def run(phases_csv: Path = PHASES_CSV, drought_path: Path = DROUGHT, out_csv: Path = OUT_CSV,
        out_json: Path | None = OUT_JSON, playbook: Path = PLAYBOOK) -> tuple[pd.DataFrame, dict]:
    phases = pd.read_csv(phases_csv, dtype=str).fillna("")
    drought = pd.read_parquet(drought_path) if str(drought_path).endswith(".parquet") else pd.read_csv(drought_path)
    table, overall = compare(phases, drought, ndma_mapping(playbook))
    p = phases[phases["ndma_phase"].isin(PHASES)]["month"]
    overall["period"] = f"{p.min()} to {p.max()}" if len(p) else None
    overall["source"] = "NDMA KnowledgeWeb county Drought Early Warning bulletins"
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(out_csv, index=False)
    if out_json:
        out_json.write_text(json.dumps(overall, indent=2, default=str))
    a = table.iloc[-1]
    print(table.to_string(index=False))
    print(f"\nOVERALL ({overall['period']}): {a.months_compared} county-months compared; exact agreement "
          f"{a.exact_agreement_pct}% (always-'Normal' baseline {a.always_normal_baseline_pct}%), within one level "
          f"{a.within_one_level_pct}%; NDMA escalations {a.ndma_escalations}: we were earlier {a.we_earlier}, same month "
          f"{a.same_month}, later {a.we_later}, not within {WINDOW} months {a.not_matched}.")
    return table, overall


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("step", nargs="?", default="compare", choices=["extract", "compare", "all"])
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--retry-na", action="store_true", help="re-read bulletins previously recorded as not available")
    a = ap.parse_args(argv)
    if a.step in ("extract", "all"):
        extract(workers=a.workers, retry_na=a.retry_na)
    if a.step in ("compare", "all"):
        run()


if __name__ == "__main__":
    sys.exit(main())
