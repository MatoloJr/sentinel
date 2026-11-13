"""Weather behaviour: climatology, seasons, trends with significance and yearly extremes."""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from . import config as C

MONTH_ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
SEASONS = {"JF": [1, 2], "MAM": [3, 4, 5], "JJAS": [6, 7, 8, 9], "OND": [10, 11, 12]}


def complete_years(daily: pd.DataFrame) -> list[int]:
    """Years with (almost) every day present, so annual totals are comparable."""
    n = daily.groupby([daily["county"], daily["date"].dt.year]).size()
    ok = n[n >= 360].reset_index()["date"].unique()
    return sorted(int(y) for y in ok)


def monthly(daily: pd.DataFrame) -> pd.DataFrame:
    """Monthly totals (rain) and means (temperature) per county."""
    g = daily.groupby(["county", pd.Grouper(key="date", freq="MS")])
    m = g.agg(precip=("precip", "sum"), tmax=("tmax", "mean"), tmin=("tmin", "mean"),
              tmean=("tmean", "mean"), ndays=("precip", "size")).reset_index()
    full = m["date"].dt.days_in_month == m["ndays"]
    return m[full].drop(columns="ndays").reset_index(drop=True)


def climatology(mon: pd.DataFrame, y0: int = C.NORMAL_START, y1: int = C.NORMAL_END) -> pd.DataFrame:
    """1991-2020 monthly normals per county (mean, median, p33, p67 of monthly rain)."""
    base = mon[(mon["date"].dt.year >= y0) & (mon["date"].dt.year <= y1)].copy()
    base["month"] = base["date"].dt.month
    clim = base.groupby(["county", "month"]).agg(
        precip_mean=("precip", "mean"), precip_median=("precip", "median"),
        precip_p33=("precip", lambda s: s.quantile(1 / 3)),
        precip_p67=("precip", lambda s: s.quantile(2 / 3)),
        tmax_mean=("tmax", "mean"), tmin_mean=("tmin", "mean"),
    ).reset_index()
    return clim


def rainy_seasons(clim: pd.DataFrame) -> pd.DataFrame:
    """Wet months = monthly normal above the county's mean monthly rainfall (annual/12).

    Contiguous wet months are joined into named seasons, e.g. 'Mar-May' and 'Oct-Dec'
    for bimodal counties. Returns one row per county.
    """
    rows = []
    for county, g in clim.groupby("county"):
        g = g.sort_values("month")
        thr = g["precip_mean"].mean()
        wet = (g["precip_mean"] > thr).to_numpy()
        runs, cur = [], []
        for i in range(12):
            if wet[i]:
                cur.append(i + 1)
            elif cur:
                runs.append(cur)
                cur = []
        if cur:
            runs.append(cur)
        if len(runs) > 1 and runs[0][0] == 1 and runs[-1][-1] == 12:  # wrap Dec-Jan
            runs[0] = runs.pop() + runs[0]
        names = [f"{MONTH_ABBR[r[0] - 1]}-{MONTH_ABBR[r[-1] - 1]}" if len(r) > 1 else MONTH_ABBR[r[0] - 1]
                 for r in runs]
        share = [g[g["month"].isin(r)]["precip_mean"].sum() / g["precip_mean"].sum() for r in runs]
        peak = int(g.loc[g["precip_mean"].idxmax(), "month"])
        rows.append({
            "county": county, "annual_normal_mm": round(g["precip_mean"].sum(), 1),
            "n_rainy_seasons": len(runs),
            "rainy_seasons": "; ".join(f"{n} ({s:.0%} of annual)" for n, s in zip(names, share)),
            "wettest_month": MONTH_ABBR[peak - 1],
            "driest_month": MONTH_ABBR[int(g.loc[g["precip_mean"].idxmin(), "month"]) - 1],
            "regime": {1: "unimodal", 2: "bimodal"}.get(len(runs), f"{len(runs)} peaks"),
        })
    return pd.DataFrame(rows)


def mann_kendall_sen(years: np.ndarray, values: np.ndarray) -> dict:
    """Mann-Kendall trend test (Kendall's tau vs time, tie-corrected) + Sen's slope."""
    mask = ~np.isnan(values)
    x, y = years[mask], values[mask]
    if len(y) < 10:
        return {"n": int(len(y)), "tau": np.nan, "p_value": np.nan, "sen_slope": np.nan,
                "slope_lo": np.nan, "slope_hi": np.nan}
    tau, p = stats.kendalltau(x, y)
    slope, _, lo, hi = stats.theilslopes(y, x, alpha=0.95)
    return {"n": int(len(y)), "tau": float(tau), "p_value": float(p), "sen_slope": float(slope),
            "slope_lo": float(lo), "slope_hi": float(hi)}


def _trend_rows(series: pd.DataFrame, value_col: str, label: str, unit: str) -> list[dict]:
    rows = []
    for county, g in series.groupby("county"):
        r = mann_kendall_sen(g["year"].to_numpy(float), g[value_col].to_numpy(float))
        mean = g[value_col].mean()
        span = g["year"].max() - g["year"].min()
        change = r["sen_slope"] * span
        rows.append({
            "county": county, "variable": label, "unit": unit, "years": f"{g['year'].min()}-{g['year'].max()}",
            "mean": mean, "sen_slope_per_decade": r["sen_slope"] * 10,
            "slope_95ci_per_decade": f"[{r['slope_lo'] * 10:.2f}, {r['slope_hi'] * 10:.2f}]",
            "total_change": change,
            "change_pct_of_mean": 100 * change / mean if unit == "mm" and mean else np.nan,
            "kendall_tau": r["tau"], "p_value": r["p_value"],
            "significant_5pct": bool(r["p_value"] < 0.05) if not np.isnan(r["p_value"]) else False,
        })
    return rows


def trends(daily: pd.DataFrame) -> pd.DataFrame:
    """Trends in annual + seasonal rainfall and annual mean Tmax/Tmin (complete years only)."""
    yrs = complete_years(daily)
    d = daily[daily["date"].dt.year.isin(yrs)].copy()
    d["year"] = d["date"].dt.year
    ann = d.groupby(["county", "year"]).agg(precip=("precip", "sum"), tmax=("tmax", "mean"),
                                            tmin=("tmin", "mean")).reset_index()
    rows = _trend_rows(ann, "precip", "Annual rainfall", "mm")
    rows += _trend_rows(ann, "tmax", "Annual mean Tmax", "degC")
    rows += _trend_rows(ann, "tmin", "Annual mean Tmin", "degC")
    for s in ("MAM", "OND"):
        sub = d[d["date"].dt.month.isin(SEASONS[s])]
        seas = sub.groupby(["county", "year"])["precip"].sum().reset_index()
        rows += _trend_rows(seas, "precip", f"{s} rainfall", "mm")
    return pd.DataFrame(rows)


def wet_day_p95(daily: pd.DataFrame) -> pd.Series:
    base = daily[daily["date"].dt.year.between(C.NORMAL_START, C.NORMAL_END)]
    wet = base[base["precip"] >= C.WET_DAY_MM]
    return wet.groupby("county")["precip"].quantile(C.HEAVY_DAY_PCTL / 100)


def _longest_run(mask: np.ndarray) -> int:
    best = cur = 0
    for v in mask:
        cur = cur + 1 if v else 0
        best = max(best, cur)
    return best


def yearly_extremes(daily: pd.DataFrame) -> pd.DataFrame:
    """Per county-year: longest dry spell, heavy-rain days (> own p95 of wet days),
    max 3-day rainfall, hot days (apparent Tmax > own p95). Dry spells are counted
    within the calendar year (a spell crossing 31 Dec is split)."""
    yrs = complete_years(daily)
    p95 = wet_day_p95(daily)
    base = daily[daily["date"].dt.year.between(C.NORMAL_START, C.NORMAL_END)]
    hot_thr = base.groupby("county")["atmax"].quantile(C.HEAT_PCTL / 100) if "atmax" in daily else None
    rows = []
    for county, g in daily.groupby("county"):
        g = g.sort_values("date").copy()
        g["r3"] = g["precip"].rolling(3, min_periods=3).sum()
        for y, gy in g.groupby(g["date"].dt.year):
            if y not in yrs:
                continue
            row = {
                "county": county, "year": int(y),
                "longest_dry_spell_days": _longest_run((gy["precip"] < C.WET_DAY_MM).to_numpy()),
                "heavy_rain_days": int((gy["precip"] > p95[county]).sum()),
                "max_3day_rain_mm": float(gy["r3"].max()),
                "annual_rain_mm": float(gy["precip"].sum()),
            }
            if hot_thr is not None:
                row["hot_days"] = int((gy["atmax"] > hot_thr[county]).sum())
            rows.append(row)
    return pd.DataFrame(rows)


def extremes_trends(ext: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for col, unit in [("longest_dry_spell_days", "days"), ("heavy_rain_days", "days"),
                      ("max_3day_rain_mm", "mm"), ("hot_days", "days")]:
        if col in ext:
            rows += _trend_rows(ext.rename(columns={col: "v"}), "v", col, unit)
    return pd.DataFrame(rows)
