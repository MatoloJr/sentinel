"""Train, tune and register the seasonal outlook model (local, Docker or Google Colab).

    python -m sentinel.train --config configs/outlook.yaml            # full search
    python -m sentinel.train --config configs/outlook.yaml --trials 5 # quick run
    python -m sentinel.train --no-promote                             # never change the active model

Pipeline
1. Outer split (unchanged from outlook.py): the last TEST_YEARS complete years are a held-out test set.
2. Rolling-origin CV inside the training period: for each fold start F, every statistic is rebuilt
   from months before F only, the model trains on targets ending before F and validates on the
   next `fold_years`. This mimics issuing forecasts year after year.
3. Optuna searches model type, hyper-parameters, feature set and calibration to minimise the mean
   CV Brier score. The warning threshold maximises the Peirce skill score on out-of-fold forecasts.
4. The best config is refit on the full training period and verified ONCE on the test set
   (sentinel/metrics.py: BSS + bootstrap CI, reliability/ECE, ROC/PR AUC, POD/FAR/CSI/PSS/HSS,
   relative economic value, per-county and per-season breakdowns).
5. A live model is fitted on all complete targets and saved with a model card to models/.
   It becomes active only if it passes model_registry.promotion_decision.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import climate, metrics as M, model_registry, outlook
from . import config as C

DEFAULT_CONFIG = {
    "n_trials": 40,
    "seed": 0,
    "cv": {"n_folds": 4, "fold_years": 2},
    "search": {
        "kinds": ["logistic", "gbm"],
        "calibration": [None, "sigmoid", "isotonic"],
        "feature_sets": {
            "base": outlook.NUM_FEATURES,
            "base+drivers": outlook.NUM_FEATURES + ["dmi_change_3m", "oni_x_ond", "dmi_x_ond"],
            "all": outlook.ALL_NUM_FEATURES,
        },
        "logistic": {"C": [0.01, 3.0]},
        "gbm": {"max_depth": [2, 5], "learning_rate": [0.01, 0.2], "max_iter": [50, 400],
                "min_samples_leaf": [20, 120], "l2_regularization": [0.0, 5.0]},
    },
    "threshold_grid": [0.34, 0.6, 0.02],
}


def load_config(path: Path | None) -> dict:
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    if path:
        import yaml
        user = yaml.safe_load(Path(path).read_text()) or {}
        for k, v in user.items():
            if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                cfg[k].update(v)
            else:
                cfg[k] = v
    return cfg


def load_inputs() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Monthly county data + climate indices; built from raw daily data if outputs/ is empty."""
    mp = C.OUT_DIR / "monthly.parquet"
    if mp.exists():
        mon = pd.read_parquet(mp)
    else:
        daily = pd.read_parquet(C.RAW_DIR / "daily_all.parquet")
        daily["date"] = pd.to_datetime(daily["date"])
        mon = climate.monthly(daily)
    mon["date"] = pd.to_datetime(mon["date"])
    idx = pd.read_parquet(C.RAW_DIR / "climate_indices.parquet")
    idx["date"] = pd.to_datetime(idx["date"])
    return mon, idx


# ---------------------------------------------------------------- CV folds
def make_folds(mon, idx, test_start: pd.Timestamp, n_folds: int, fold_years: int) -> list[dict]:
    """Rolling-origin folds ending at test_start; panels rebuilt per fold (no future statistics)."""
    folds = []
    for k in range(n_folds, 0, -1):
        start = pd.Timestamp(test_start.year - k * fold_years, 1, 1)
        end = pd.Timestamp(start.year + fold_years, 1, 1)
        panel, _ = outlook.build_panel(mon, idx, start)
        tr = outlook._fit_rows(panel, start)
        va = outlook._test_rows(panel, start)
        va = va[va["target_end"] < min(end, test_start)]  # purge: validation targets stay before the next fold/test
        if len(tr) and va["y"].nunique() == 2:
            folds.append({"start": start, "train": tr, "valid": va})
    return folds


def _suggest(trial, cfg: dict) -> dict:
    s = cfg["search"]
    kind = trial.suggest_categorical("kind", s["kinds"])
    fs = trial.suggest_categorical("feature_set", list(s["feature_sets"]))
    cal = trial.suggest_categorical("calibration", [str(c) for c in s["calibration"]])
    params = {}
    if kind == "logistic":
        params["C"] = trial.suggest_float("C", *s["logistic"]["C"], log=True)
    else:
        g = s["gbm"]
        params = {"max_depth": trial.suggest_int("max_depth", *g["max_depth"]),
                  "learning_rate": trial.suggest_float("learning_rate", *g["learning_rate"], log=True),
                  "max_iter": trial.suggest_int("max_iter", *g["max_iter"], step=25),
                  "min_samples_leaf": trial.suggest_int("min_samples_leaf", *g["min_samples_leaf"]),
                  "l2_regularization": trial.suggest_float("l2_regularization", *g["l2_regularization"])}
    return {"chosen": kind, "params": params, "num_features": list(s["feature_sets"][fs]), "feature_set": fs,
            "calibration": None if cal == "None" else cal}


def cv_score(sel: dict, folds: list[dict]) -> tuple[float, pd.DataFrame]:
    feats = outlook.features_of(sel)
    briers, oof = [], []
    for f in folds:
        m = outlook.make_from_selection(sel).fit(f["train"][feats], f["train"]["y"].astype(int))
        p = m.predict_proba(f["valid"][feats])[:, 1]
        briers.append(M.brier(f["valid"]["y"], p))
        oof.append(pd.DataFrame({"y": f["valid"]["y"].to_numpy(), "p": p, "fold": str(f["start"].date())}))
    return float(np.mean(briers)), pd.concat(oof, ignore_index=True)


def pick_threshold(oof: pd.DataFrame, grid: list[float]) -> float:
    lo, hi, step = grid
    best_t, best = lo, -np.inf
    for t in np.round(np.arange(lo, hi + 1e-9, step), 2):
        pss = M.categorical_scores(oof["y"].astype(int), oof["p"] >= t)["pss"]
        if np.isfinite(pss) and pss > best:
            best_t, best = float(t), pss
    return best_t


# ---------------------------------------------------------------- main entry
def train(cfg: dict, promote: bool = True, verbose: bool = True) -> dict:
    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    mon, idx = load_inputs()
    sd = outlook.split_dates(mon)
    test_start = sd["test_start"]
    folds = make_folds(mon, idx, test_start, cfg["cv"]["n_folds"], cfg["cv"]["fold_years"])
    if not folds:
        raise RuntimeError("No usable CV folds: not enough training years.")
    if verbose:
        print(f"CV folds: {[str(f['start'].date()) for f in folds]} | test from {test_start.date()}")

    def objective(trial):
        sel = _suggest(trial, cfg)
        score, _ = cv_score(sel, folds)
        return score

    study = optuna.create_study(direction="minimize", sampler=optuna.samplers.TPESampler(seed=cfg["seed"]))
    study.optimize(objective, n_trials=int(cfg["n_trials"]), show_progress_bar=verbose)
    best = _suggest(optuna.trial.FixedTrial(study.best_params), cfg)
    cv_brier, oof = cv_score(best, folds)
    best["threshold"] = pick_threshold(oof, cfg["threshold_grid"])
    clim_cv = M.brier(oof["y"], np.full(len(oof), M.CLIM_P))
    if verbose:
        print(f"Best CV Brier {cv_brier:.4f} (climatology {clim_cv:.4f}) -> {best['chosen']} "
              f"{best['feature_set']} cal={best['calibration']} thr={best['threshold']}")

    # ---- one-shot test verification
    feats = outlook.features_of(best)
    panel, meta = outlook.build_panel(mon, idx, test_start)
    tr, te = outlook._fit_rows(panel, test_start), outlook._test_rows(panel, test_start).copy()
    model = outlook.make_from_selection(best).fit(tr[feats], tr["y"].astype(int))
    te["p_model"] = model.predict_proba(te[feats])[:, 1]
    cond = tr.groupby("persist_dry")["y"].mean()
    te["p_persist"] = te["persist_dry"].map(cond).fillna(1 / 3)
    test_report = M.evaluate_probabilistic(te, "p_model", threshold=best["threshold"], ref_col="p_persist")
    te["season"] = te["issue_date"].dt.month.map(outlook.SEASON_OF_ISSUE).fillna("other")
    by_county = M.breakdown(te, "county", threshold=best["threshold"])
    by_season = M.breakdown(te[te["season"] != "other"], "season", threshold=best["threshold"])

    # ---- live model on every complete target
    last = mon["date"].max()
    live_panel, _ = outlook.build_panel(mon, idx, last + pd.DateOffset(months=1))
    live_tr = live_panel[(live_panel["target_end"] <= last) & live_panel["eligible"] & live_panel["y"].notna()]
    live_model = outlook.make_from_selection(best).fit(live_tr[feats], live_tr["y"].astype(int))

    card = {
        "task": "P(next-3-month rainfall in driest tercile) per Kenyan county",
        "model": {"kind": best["chosen"], "params": best["params"], "num_features": best["num_features"],
                  "feature_set": best["feature_set"], "categorical_features": outlook.CAT_FEATURES,
                  "calibration": best["calibration"], "threshold": best["threshold"]},
        "data": {"monthly_from": str(mon["date"].min().date()), "monthly_to": str(last.date()),
                 "test_start": str(test_start.date()), "n_train": int(len(tr)), "n_test": int(len(te)),
                 "n_live_train": int(len(live_tr)), "stats_window": meta},
        "cv": {"folds": [str(f["start"].date()) for f in folds], "brier": cv_brier, "brier_climatology": clim_cv,
               "bss": 1 - cv_brier / clim_cv if clim_cv else None, "n_trials": int(cfg["n_trials"])},
        "test": {k: v for k, v in test_report.items() if k not in ("reliability", "relative_value")},
        "reliability": test_report["reliability"],
        "relative_value": test_report["relative_value"],
        "by_county": by_county.round(4).to_dict(orient="records"),
        "by_season": by_season.round(4).to_dict(orient="records"),
        "config": cfg,
    }
    import sklearn
    card["environment"] = {"sklearn": sklearn.__version__}
    path = model_registry.save(live_model, card)
    card = model_registry.load_card(path.name)
    ok, why = model_registry.promotion_decision(card, model_registry.active_card())
    if promote and ok:
        model_registry.promote(card["version"], why)
    card["promotion"] = {"promoted": bool(promote and ok), "reason": why if promote else "promotion disabled"}
    (path / "model_card.json").write_text(json.dumps(card, indent=2, default=str))
    if verbose:
        t = card["test"]
        print(f"Test: BSS {t['bss_vs_climatology']:.3f} CI [{t['bss_90ci'][0]:.3f}, {t['bss_90ci'][1]:.3f}] | "
              f"AUC {t['roc_auc']:.3f} | ECE {t['ece']:.3f} | PSS {t['cat_pss']:.3f}")
        print(f"Saved {path} | promoted: {card['promotion']['promoted']} ({card['promotion']['reason']})")
    return card


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", type=Path, default=C.ROOT / "configs" / "outlook.yaml")
    ap.add_argument("--trials", type=int, help="override n_trials")
    ap.add_argument("--no-promote", action="store_true")
    a = ap.parse_args(argv)
    cfg = load_config(a.config if a.config and a.config.exists() else None)
    if a.trials:
        cfg["n_trials"] = a.trials
    train(cfg, promote=not a.no_promote)


if __name__ == "__main__":
    main()
