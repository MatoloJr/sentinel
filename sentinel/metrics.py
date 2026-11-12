"""Verification metrics for probabilistic and yes/no climate forecasts.

Used by the outlook backtest, the Colab training notebook, the model card and the dashboard.
References: Wilks, *Statistical Methods in the Atmospheric Sciences* (ch. 9); Richardson (2000)
for relative economic value; WMO SVS-LRF for long-range forecast verification.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

CLIM_P = 1 / 3  # climatological probability of the below-normal tercile


# ---------------------------------------------------------------- probabilistic
def brier(y, p) -> float:
    return float(brier_score_loss(np.asarray(y, int), np.asarray(p, float)))


def bss(y, p, ref=CLIM_P) -> float:
    """Brier skill score vs a reference probability (scalar or array). > 0 = better than reference."""
    y = np.asarray(y, int)
    ref_p = np.full(len(y), ref, float) if np.isscalar(ref) else np.asarray(ref, float)
    b_ref = brier_score_loss(y, ref_p)
    return float(1 - brier(y, p) / b_ref) if b_ref > 0 else float("nan")


def reliability(y, p, n_bins: int = 10) -> pd.DataFrame:
    """Reliability-diagram table: mean forecast vs observed frequency per probability bin."""
    y, p = np.asarray(y, float), np.asarray(p, float)
    edges = np.linspace(0, 1, n_bins + 1)
    b = np.clip(np.digitize(p, edges[1:-1]), 0, n_bins - 1)
    rows = []
    for i in range(n_bins):
        m = b == i
        if m.any():
            rows.append({"bin_lo": edges[i], "bin_hi": edges[i + 1], "n": int(m.sum()),
                         "mean_forecast": float(p[m].mean()), "observed_freq": float(y[m].mean())})
    return pd.DataFrame(rows)


def ece(y, p, n_bins: int = 10) -> float:
    """Expected calibration error: n-weighted |forecast - observed| over bins (0 = perfectly reliable)."""
    r = reliability(y, p, n_bins)
    if r.empty:
        return float("nan")
    return float((r["n"] * (r["mean_forecast"] - r["observed_freq"]).abs()).sum() / r["n"].sum())


def roc_auc(y, p) -> float:
    try:
        return float(roc_auc_score(np.asarray(y, int), p))
    except ValueError:
        return float("nan")


def pr_auc(y, p) -> float:
    try:
        return float(average_precision_score(np.asarray(y, int), p))
    except ValueError:
        return float("nan")


# ---------------------------------------------------------------- categorical (contingency table)
def contingency(y, warn) -> dict:
    y, w = np.asarray(y, bool), np.asarray(warn, bool)
    return {"hits": int((y & w).sum()), "false_alarms": int((~y & w).sum()),
            "misses": int((y & ~w).sum()), "correct_negatives": int((~y & ~w).sum())}


def categorical_scores(y, warn) -> dict:
    """POD, FAR (false-alarm ratio), POFD, CSI, Peirce (Hanssen-Kuipers) and Heidke skill scores."""
    t = contingency(y, warn)
    a, b, c, d = t["hits"], t["false_alarms"], t["misses"], t["correct_negatives"]
    n = a + b + c + d
    div = lambda x, y_: x / y_ if y_ else float("nan")  # noqa: E731
    pod, pofd = div(a, a + c), div(b, b + d)
    exp_correct = div((a + c) * (a + b) + (b + d) * (c + d), n)
    return {**t, "pod": pod, "far": div(b, a + b), "pofd": pofd, "csi": div(a, a + b + c),
            "pss": pod - pofd if not (np.isnan(pod) or np.isnan(pofd)) else float("nan"),
            "hss": div(a + d - exp_correct, n - exp_correct), "bias": div(a + b, a + c)}


# ---------------------------------------------------------------- decision value
def relative_value(y, p, cost_loss: np.ndarray | None = None, thresholds: np.ndarray | None = None) -> pd.DataFrame:
    """Richardson (2000) relative economic value for a user with cost/loss ratio alpha = C/L.

    Acting costs C; an unprotected event loses L. V = (E_clim - E_fcst) / (E_clim - E_perfect).
    V = 1: as good as a perfect forecast; V <= 0: no better than always/never acting.
    For each alpha the best probability threshold is used (envelope curve).
    """
    y = np.asarray(y, bool)
    p = np.asarray(p, float)
    alphas = np.round(np.arange(0.05, 1.0, 0.05), 2) if cost_loss is None else np.asarray(cost_loss)
    thr = np.round(np.arange(0.05, 0.96, 0.05), 2) if thresholds is None else np.asarray(thresholds)
    s = y.mean()
    rows = []
    for al in alphas:
        e_clim = min(al, s)          # expense per unit loss: always act (alpha) or never act (s)
        e_perf = s * al
        best_v, best_t = -np.inf, None
        for t in thr:
            w = p >= t
            h, f = (y & w).mean(), (~y & w).mean()
            m = (y & ~w).mean()
            e_fc = al * (h + f) + m
            v = (e_clim - e_fc) / (e_clim - e_perf) if e_clim > e_perf else np.nan
            if v > best_v:
                best_v, best_t = v, t
        rows.append({"cost_loss": float(al), "value": float(best_v), "best_threshold": best_t})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- ranked probability (terciles)
def rpss(y_cat, probs, clim=(1 / 3, 1 / 3, 1 / 3)) -> float:
    """Ranked probability skill score for 3-category (tercile) forecasts.
    y_cat in {0,1,2}; probs shape (n, 3)."""
    y_cat = np.asarray(y_cat, int)
    probs = np.asarray(probs, float)
    obs = np.eye(3)[y_cat]
    rps = ((np.cumsum(probs, 1) - np.cumsum(obs, 1)) ** 2).sum(1).mean()
    rps_ref = ((np.cumsum(np.tile(clim, (len(y_cat), 1)), 1) - np.cumsum(obs, 1)) ** 2).sum(1).mean()
    return float(1 - rps / rps_ref) if rps_ref > 0 else float("nan")


# ---------------------------------------------------------------- bootstrap
def block_bootstrap(df: pd.DataFrame, fn, n: int = 500, block_col: str = "year", seed: int = 0,
                    ci: tuple[float, float] = (5, 95)) -> tuple[float, float]:
    """CI for any metric fn(df) resampling whole blocks (years) to keep within-year dependence."""
    rng = np.random.default_rng(seed)
    blocks = df[block_col].unique()
    groups = {b: df[df[block_col] == b] for b in blocks}
    vals = []
    for _ in range(n):
        s = pd.concat([groups[b] for b in rng.choice(blocks, size=len(blocks), replace=True)])
        v = fn(s)
        if v is not None and np.isfinite(v):
            vals.append(v)
    if not vals:
        return float("nan"), float("nan")
    return float(np.percentile(vals, ci[0])), float(np.percentile(vals, ci[1]))


# ---------------------------------------------------------------- one-call report
def evaluate_probabilistic(df: pd.DataFrame, p_col: str = "p_model", y_col: str = "y", threshold: float = 0.5,
                           ref_col: str | None = "p_persist", n_boot: int = 300) -> dict:
    """Full verification report for a test set with columns y, p_col, issue_date (and optional ref_col)."""
    d = df.dropna(subset=[y_col, p_col]).copy()
    d["year"] = pd.to_datetime(d["issue_date"]).dt.year
    y, p = d[y_col].astype(int).to_numpy(), d[p_col].to_numpy()
    lo, hi = block_bootstrap(d, lambda s: bss(s[y_col].astype(int), s[p_col]) if s[y_col].nunique() > 1 else None,
                             n=n_boot)
    rep = {
        "n": int(len(d)), "base_rate": float(y.mean()) if len(y) else float("nan"),
        "brier": brier(y, p), "bss_vs_climatology": bss(y, p), "bss_90ci": [lo, hi],
        "roc_auc": roc_auc(y, p), "pr_auc": pr_auc(y, p), "ece": ece(y, p),
        "threshold": threshold, **{f"cat_{k}": v for k, v in categorical_scores(y, p >= threshold).items()},
    }
    if ref_col and ref_col in d:
        rep["bss_vs_persistence"] = bss(y, p, d[ref_col].to_numpy())
    rep["reliability"] = reliability(y, p).to_dict(orient="records")
    rep["relative_value"] = relative_value(y, p).to_dict(orient="records")
    return rep


def breakdown(df: pd.DataFrame, by: str, p_col: str = "p_model", y_col: str = "y", threshold: float = 0.5) -> pd.DataFrame:
    """Key metrics per group (county, issue month / season, zone)."""
    rows = []
    for k, g in df.dropna(subset=[y_col, p_col]).groupby(by):
        y, p = g[y_col].astype(int), g[p_col]
        cs = categorical_scores(y, p >= threshold)
        rows.append({by: k, "n": len(g), "base_rate": y.mean(), "brier": brier(y, p), "bss": bss(y, p),
                     "roc_auc": roc_auc(y, p), "ece": ece(y, p), "pod": cs["pod"], "far": cs["far"],
                     "pss": cs["pss"], "hss": cs["hss"]})
    return pd.DataFrame(rows)
