"""Seasonal outlook: will the next 3 months' rainfall fall in the driest third (below normal)?

Leakage rules (tested in tests/test_outlook_leakage.py):
* Time split: test = issue months whose 3-month target starts on/after 1 Jan of the first of the
  last TEST_YEARS complete years. Training targets must END before the test period (purged gap).
* Every normal, standard deviation and tercile threshold is computed from training months only.
* Climate indices use only values published by the issue date: ONI season ending the previous
  month (centred two months back) and DMI of the previous month.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, f1_score, precision_score, recall_score, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from . import config as C

NUM_FEATURES = ["rain_z_1m", "rain_z_3m", "tmean_anom_3m", "oni_lag", "oni_change_3m", "dmi_lag",
                "target_month_sin", "target_month_cos", "log_clim_target_mm"]
CAT_FEATURES = ["zone"]
SEASON_OF_ISSUE = {2: "MAM (issued end Feb)", 9: "OND (issued end Sep)"}


# ---------------------------------------------------------------- split helpers
def split_dates(mon: pd.DataFrame, test_years: int = C.TEST_YEARS) -> dict:
    last = mon["date"].max()
    last_complete_year = last.year if last.month == 12 else last.year - 1
    test_start = pd.Timestamp(last_complete_year - test_years + 1, 1, 1)
    return {"test_start": test_start, "last_month": last, "last_complete_year": last_complete_year}


# ---------------------------------------------------------------- features
def build_panel(mon: pd.DataFrame, idx: pd.DataFrame, train_end: pd.Timestamp) -> tuple[pd.DataFrame, dict]:
    """One row per county x issue month. Statistics use months with date < train_end only."""
    zone = {c.name: c.zone for c in C.COUNTIES}
    idx = idx.set_index("date").sort_index()
    rows = []
    meta = {"stats_from": None, "stats_to": None}
    for county, g in mon.groupby("county"):
        g = g.sort_values("date").set_index("date").asfreq("MS")
        p, t = g["precip"], g["tmean"]
        p3 = p.rolling(3, min_periods=3).sum()
        tgt = p.shift(-1) + p.shift(-2) + p.shift(-3)  # next 3 months
        df = pd.DataFrame({"county": county, "precip_1m": p, "precip_3m": p3, "target_mm": tgt})
        df["month"] = df.index.month
        df["target_start_month"] = (df["month"] % 12) + 1
        df["target_end"] = df.index + pd.DateOffset(months=3)

        tr = df.index < train_end                        # training months for 1- and 3-month stats
        tr_target = df["target_end"] < train_end         # target window fully inside training
        meta["stats_from"] = str(df.index[tr].min().date()) if tr.any() else None
        meta["stats_to"] = str(df.index[tr].max().date()) if tr.any() else None

        m1 = df[tr].groupby("month")["precip_1m"].agg(["mean", "std"])
        m3 = df[tr].groupby("month")["precip_3m"].agg(["mean", "std"])
        tn = pd.DataFrame({"t": t, "month": df["month"]})[tr].groupby("month")["t"].mean()
        tq = df[tr_target].groupby("target_start_month")["target_mm"].agg(
            p33=lambda s: s.quantile(1 / 3), clim="mean")
        p3_q = df[tr].groupby("month")["precip_3m"].quantile(1 / 3)

        df["rain_z_1m"] = (df["precip_1m"] - df["month"].map(m1["mean"])) / df["month"].map(m1["std"]).replace(0, np.nan)
        df["rain_z_3m"] = (df["precip_3m"] - df["month"].map(m3["mean"])) / df["month"].map(m3["std"]).replace(0, np.nan)
        tanom = t - df["month"].map(tn)
        df["tmean_anom_3m"] = tanom.rolling(3, min_periods=3).mean()
        df["p33_mm"] = df["target_start_month"].map(tq["p33"])
        df["clim_target_mm"] = df["target_start_month"].map(tq["clim"])
        df["log_clim_target_mm"] = np.log1p(df["clim_target_mm"])
        df["persist_dry"] = (df["precip_3m"] < df["month"].map(p3_q)).astype(float)
        df.loc[df["precip_3m"].isna(), "persist_dry"] = np.nan
        df["y"] = (df["target_mm"] < df["p33_mm"]).astype(float)
        df.loc[df["target_mm"].isna(), "y"] = np.nan
        df["zone"] = zone.get(county, "unknown")
        rows.append(df)
    panel = pd.concat(rows).rename_axis("issue_date").reset_index()

    # Climate drivers known at issue time (publication lag respected).
    # Latest published value, carried forward at most 3 months when a release is late.
    months = pd.date_range(idx.index.min(), panel["issue_date"].max(), freq="MS")
    oni = idx["oni"].reindex(months).ffill(limit=3) if "oni" in idx else pd.Series(dtype=float)
    dmi = idx["dmi"].reindex(months).ffill(limit=3) if "dmi" in idx else pd.Series(dtype=float)
    panel["oni_lag"] = (panel["issue_date"] - pd.DateOffset(months=2)).map(oni)
    panel["oni_change_3m"] = panel["oni_lag"] - (panel["issue_date"] - pd.DateOffset(months=5)).map(oni)
    panel["dmi_lag"] = (panel["issue_date"] - pd.DateOffset(months=1)).map(dmi)
    ang = 2 * np.pi * (panel["target_start_month"] - 1) / 12
    panel["target_month_sin"], panel["target_month_cos"] = np.sin(ang), np.cos(ang)
    panel["eligible"] = panel["clim_target_mm"] >= C.DRY_SEASON_MIN_MM
    meta["train_end_exclusive"] = str(pd.Timestamp(train_end).date())
    return panel, meta


# ---------------------------------------------------------------- models
def _make_model(kind: str) -> Pipeline:
    pre = ColumnTransformer([
        ("num", Pipeline([("imp", SimpleImputer(strategy="median")), ("sc", StandardScaler())]), NUM_FEATURES),
        ("cat", OneHotEncoder(handle_unknown="ignore"), CAT_FEATURES),
    ])
    if kind == "logistic":
        clf = LogisticRegression(C=0.3, max_iter=2000)
    else:
        clf = HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=150,
                                             l2_regularization=1.0, min_samples_leaf=40, random_state=0)
    return Pipeline([("pre", pre), ("clf", clf)])


def _fit_rows(panel: pd.DataFrame, train_end: pd.Timestamp) -> pd.DataFrame:
    return panel[(panel["target_end"] < train_end) & panel["eligible"] & panel["y"].notna()]


def _test_rows(panel: pd.DataFrame, test_start: pd.Timestamp) -> pd.DataFrame:
    tgt_start = panel["issue_date"] + pd.DateOffset(months=1)
    return panel[(tgt_start >= test_start) & panel["eligible"] & panel["y"].notna()]


def select_model(mon: pd.DataFrame, idx: pd.DataFrame, test_start: pd.Timestamp) -> dict:
    """Pick model type and decision threshold on the last INNER_VALID_YEARS of the training period,
    rebuilding all statistics with the inner training years only."""
    inner_start = pd.Timestamp(test_start.year - C.INNER_VALID_YEARS, 1, 1)
    panel, _ = build_panel(mon, idx, inner_start)
    tr = _fit_rows(panel, inner_start)
    va = _test_rows(panel, inner_start)
    va = va[va["target_end"] < test_start]
    res = {}
    for kind in ("logistic", "gbm"):
        m = _make_model(kind).fit(tr[NUM_FEATURES + CAT_FEATURES], tr["y"].astype(int))
        prob = m.predict_proba(va[NUM_FEATURES + CAT_FEATURES])[:, 1]
        # A below-normal warning must say "drier than the usual 1-in-3", so thresholds start
        # above climatology; lower thresholds just warn every month and inflate F1.
        thr_grid = np.round(np.arange(0.34, 0.61, 0.02), 2)
        f1s = [f1_score(va["y"].astype(int), (prob >= t).astype(int), zero_division=0) for t in thr_grid]
        res[kind] = {"brier": float(brier_score_loss(va["y"], prob)),
                     "best_threshold": float(thr_grid[int(np.argmax(f1s))]), "best_f1": float(max(f1s))}
    best = min(res, key=lambda k: res[k]["brier"])
    return {"chosen": best, "threshold": res[best]["best_threshold"], "candidates": res,
            "inner_train_end": str(inner_start.date()), "n_inner_train": int(len(tr)), "n_inner_valid": int(len(va))}


# ---------------------------------------------------------------- evaluation
def _cls_metrics(y, pred) -> dict:
    return {"precision": precision_score(y, pred, zero_division=0),
            "recall": recall_score(y, pred, zero_division=0),
            "f1": f1_score(y, pred, zero_division=0)}


def _bss(y, p) -> float:
    ref = brier_score_loss(y, np.full(len(y), 1 / 3))
    return 1 - brier_score_loss(y, p) / ref if ref > 0 else np.nan


def _bootstrap_bss(df: pd.DataFrame, col: str, n: int, seed: int = 0) -> tuple[float, float]:
    """Block bootstrap over test years (keeps within-year dependence together)."""
    rng = np.random.default_rng(seed)
    yrs = df["issue_date"].dt.year.unique()
    by = {y: df[df["issue_date"].dt.year == y] for y in yrs}
    vals = []
    for _ in range(n):
        s = pd.concat([by[y] for y in rng.choice(yrs, size=len(yrs), replace=True)])
        if s["y"].nunique() < 2:
            continue
        vals.append(_bss(s["y"], s[col]))
    if not vals:
        return np.nan, np.nan
    return float(np.percentile(vals, 5)), float(np.percentile(vals, 95))


def verdict(bss: float, lo: float, f1_model: float, f1_best_baseline: float) -> tuple[str, str]:
    if np.isnan(bss) or bss <= 0:
        return "No skill - use climatology", "low"
    if lo > 0 and f1_model >= f1_best_baseline:
        return "Skill over both baselines", "medium"
    return "Weak or uncertain skill", "low"


def run(mon: pd.DataFrame, idx: pd.DataFrame, n_boot: int = C.BOOTSTRAP_N) -> dict:
    sd = split_dates(mon)
    test_start = sd["test_start"]
    sel = select_model(mon, idx, test_start)
    panel, meta = build_panel(mon, idx, test_start)
    tr, te = _fit_rows(panel, test_start), _test_rows(panel, test_start).copy()
    model = _make_model(sel["chosen"]).fit(tr[NUM_FEATURES + CAT_FEATURES], tr["y"].astype(int))
    te["p_model"] = model.predict_proba(te[NUM_FEATURES + CAT_FEATURES])[:, 1]
    te["pred_model"] = (te["p_model"] >= sel["threshold"]).astype(int)
    # Persistence as a probability: training frequency of 'below' given last 3 months dry / not dry.
    cond = tr.groupby("persist_dry")["y"].mean()
    te["p_persist"] = te["persist_dry"].map(cond).fillna(1 / 3)
    te["pred_persist"] = te["persist_dry"].fillna(0).astype(int)
    te["p_clim"] = 1 / 3

    rows = []
    for county, g in list(te.groupby("county")) + [("ALL (pooled)", te)]:
        y = g["y"].astype(int)
        base_rate = y.mean()
        mm, mp = _cls_metrics(y, g["pred_model"]), _cls_metrics(y, g["pred_persist"])
        # Climatology as a categorical forecast: warn at random 1-in-3 -> expected precision
        # = observed base rate, recall = 1/3.
        cp, cr = base_rate, 1 / 3
        cf = 2 * cp * cr / (cp + cr) if cp + cr > 0 else 0.0
        bss_m, bss_p = _bss(y, g["p_model"]), _bss(y, g["p_persist"])
        lo, hi = _bootstrap_bss(g, "p_model", n_boot)
        try:
            auc = roc_auc_score(y, g["p_model"])
        except ValueError:
            auc = np.nan
        v, conf = verdict(bss_m, lo, mm["f1"], max(mp["f1"], cf))
        rows.append({
            "county": county, "n_test": int(len(g)), "observed_below_rate": round(base_rate, 3),
            "model_precision": mm["precision"], "model_recall": mm["recall"], "model_f1": mm["f1"],
            "persistence_precision": mp["precision"], "persistence_recall": mp["recall"], "persistence_f1": mp["f1"],
            "climatology_precision": cp, "climatology_recall": cr, "climatology_f1": cf,
            "brier_model": brier_score_loss(y, g["p_model"]), "brier_persistence": brier_score_loss(y, g["p_persist"]),
            "brier_climatology": brier_score_loss(y, g["p_clim"]),
            "bss_model_vs_clim": bss_m, "bss_90ci_lo": lo, "bss_90ci_hi": hi,
            "bss_persistence_vs_clim": bss_p, "roc_auc_model": auc, "verdict": v, "confidence": conf,
        })
    metrics = pd.DataFrame(rows)

    seas = []
    for m, label in SEASON_OF_ISSUE.items():
        g = te[te["issue_date"].dt.month == m]
        if len(g) and g["y"].nunique() == 2:
            lo, hi = _bootstrap_bss(g, "p_model", n_boot)
            seas.append({"target_season": label, "n_test": len(g), "bss_model": _bss(g["y"], g["p_model"]),
                         "bss_90ci": f"[{lo:.2f}, {hi:.2f}]", "bss_persistence": _bss(g["y"], g["p_persist"]),
                         "model_f1": f1_score(g["y"].astype(int), g["pred_model"], zero_division=0),
                         "persistence_f1": f1_score(g["y"].astype(int), g["pred_persist"], zero_division=0)})
    by_season = pd.DataFrame(seas)

    live = live_outlook(mon, idx, sel, metrics)
    info = {"split": {k: str(v.date()) if hasattr(v, "date") else v for k, v in sd.items()},
            "selection": sel, "stats_window": meta, "n_train": int(len(tr)), "n_test": int(len(te)),
            "features": NUM_FEATURES + CAT_FEATURES,
            "train_issue_range": [str(tr["issue_date"].min().date()), str(tr["issue_date"].max().date())],
            "test_issue_range": [str(te["issue_date"].min().date()), str(te["issue_date"].max().date())]}
    return {"metrics": metrics, "by_season": by_season, "test_predictions": te, "live": live, "info": info}


def live_outlook(mon: pd.DataFrame, idx: pd.DataFrame, sel: dict, metrics: pd.DataFrame) -> pd.DataFrame:
    """Outlook issued at the end of the latest complete month, trained on ALL complete targets.
    Where the backtest showed no skill, the published probability is climatology (1/3)."""
    last = mon["date"].max()
    cutoff = last + pd.DateOffset(months=1)
    panel, _ = build_panel(mon, idx, cutoff)
    tr = panel[(panel["target_end"] <= last) & panel["eligible"] & panel["y"].notna()]
    model = _make_model(sel["chosen"]).fit(tr[NUM_FEATURES + CAT_FEATURES], tr["y"].astype(int))
    now = panel[panel["issue_date"] == last].copy()
    now["p_model"] = model.predict_proba(now[NUM_FEATURES + CAT_FEATURES])[:, 1]
    vm = metrics.set_index("county")
    out = []
    for r in now.itertuples():
        v = vm.loc[r.county] if r.county in vm.index else None
        verdict_ = v["verdict"] if v is not None else "No skill - use climatology"
        target = f"{(r.issue_date + pd.DateOffset(months=1)):%b %Y} - {(r.issue_date + pd.DateOffset(months=3)):%b %Y}"
        if not r.eligible:
            published, basis = None, "Dry season: 3-month normal below threshold, outlook not issued"
        elif verdict_.startswith("No skill"):
            published, basis = 1 / 3, "Climatology (model showed no skill in backtest)"
        else:
            published, basis = float(r.p_model), f"Model ({sel['chosen']})"
        out.append({
            "county": r.county, "issued_end_of": f"{r.issue_date:%b %Y}", "target_months": target,
            "prob_below_normal": None if published is None else round(published, 2),
            "model_raw_prob": round(float(r.p_model), 2), "basis": basis, "backtest_verdict": verdict_,
            "confidence": "low" if v is None else v["confidence"],
            "bss_backtest": None if v is None else round(float(v["bss_model_vs_clim"]), 2),
            "below_normal_threshold_mm": round(float(r.p33_mm), 1) if pd.notna(r.p33_mm) else None,
            "normal_mm": round(float(r.clim_target_mm), 1) if pd.notna(r.clim_target_mm) else None,
            "oni_used": r.oni_lag, "dmi_used": r.dmi_lag,
            "inputs_missing": ", ".join(k for k in ("oni_lag", "dmi_lag") if pd.isna(getattr(r, k))) or "none",
        })
    return pd.DataFrame(out)


def save(res: dict, out_dir) -> None:
    res["metrics"].round(3).to_csv(out_dir / "outlook_metrics.csv", index=False)
    res["by_season"].round(3).to_csv(out_dir / "outlook_by_season.csv", index=False)
    res["live"].to_csv(out_dir / "outlook_live.csv", index=False)
    res["test_predictions"].to_parquet(out_dir / "outlook_test_predictions.parquet", index=False)
    (out_dir / "outlook_info.json").write_text(json.dumps(res["info"], indent=2, default=str))
