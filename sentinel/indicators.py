"""Hazard indicators (drought, heavy rain, heat) and their validation against documented events."""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config as C


# ---------------------------------------------------------------- drought
def drought_level(pct: float) -> str:
    if pct is None or np.isnan(pct):
        return "Not assessed"
    for lo, hi, lvl in C.DROUGHT_CLASSES:
        if lo <= pct < hi:
            return lvl
    return "Not assessed"


def drought_indicator(mon: pd.DataFrame) -> pd.DataFrame:
    """3-month rainfall (ending in `date`'s month) as % of the 1991-2020 normal for the
    same 3 calendar months. Windows whose normal is below DRY_SEASON_MIN_MM are dry season:
    a % of a tiny normal is noise, so they are 'Not assessed' instead of a false alarm."""
    out = []
    for county, g in mon.groupby("county"):
        g = g.sort_values("date").set_index("date")
        g = g.asfreq("MS")  # expose gaps so the 3-month window never spans a hole
        r3 = g["precip"].rolling(3, min_periods=3).sum()
        df = pd.DataFrame({"county": county, "rain_3m_mm": r3})
        df["month"] = df.index.month
        base = df[(df.index.year >= C.NORMAL_START) & (df.index.year <= C.NORMAL_END)]
        normal = base.groupby("month")["rain_3m_mm"].mean()
        df["normal_3m_mm"] = df["month"].map(normal)
        df["pct_of_normal"] = 100 * df["rain_3m_mm"] / df["normal_3m_mm"]
        dry = df["normal_3m_mm"] < C.DRY_SEASON_MIN_MM
        df.loc[dry, "pct_of_normal"] = np.nan
        df["level"] = df["pct_of_normal"].map(drought_level)
        df.loc[dry, "level"] = "Dry season (not assessed)"
        out.append(df.dropna(subset=["rain_3m_mm"]).reset_index())
    return pd.concat(out, ignore_index=True)


def drought_class_frequency(dro: pd.DataFrame) -> pd.DataFrame:
    """How often each class occurred in 1991-2020 (justifies the class edges)."""
    base = dro[dro["date"].dt.year.between(C.NORMAL_START, C.NORMAL_END)]
    t = pd.crosstab(base["county"], base["level"], normalize="index").mul(100).round(1)
    return t.reindex(columns=[c for c in C.LEVELS + ["Dry season (not assessed)"] if c in t.columns])


# ---------------------------------------------------------------- heavy rain
def heavy_thresholds(daily: pd.DataFrame) -> pd.DataFrame:
    """County percentiles of the rolling 3-day total over 1991-2020 (all days)."""
    rows = []
    for county, g in daily.groupby("county"):
        g = g.sort_values("date")
        r3 = g["precip"].rolling(3, min_periods=3).sum()
        base = r3[g["date"].dt.year.between(C.NORMAL_START, C.NORMAL_END)].dropna()
        row = {"county": county}
        for lvl, p in C.HEAVY_PCTLS.items():
            row[f"p{p:g}_3day_mm"] = float(base.quantile(p / 100))
        rows.append(row)
    return pd.DataFrame(rows).set_index("county")


def heavy_level(value: float, thr: pd.Series) -> str:
    if value is None or np.isnan(value):
        return "Not assessed"
    lvl = "Normal"
    for name, p in C.HEAVY_PCTLS.items():
        if value >= thr[f"p{p:g}_3day_mm"]:
            lvl = name
    return lvl


def heavy_rain_indicator(daily: pd.DataFrame, thr: pd.DataFrame) -> pd.DataFrame:
    out = []
    for county, g in daily.groupby("county"):
        g = g.sort_values("date")[["county", "date", "precip"]].copy()
        g["rain_3d_mm"] = g["precip"].rolling(3, min_periods=3).sum()
        t = thr.loc[county]
        g["p99_3day_mm"] = t["p99_3day_mm"]
        g["ratio_to_p99"] = g["rain_3d_mm"] / t["p99_3day_mm"]
        g["level"] = [heavy_level(v, t) for v in g["rain_3d_mm"]]
        out.append(g)
    return pd.concat(out, ignore_index=True)


# ---------------------------------------------------------------- worst events + validation
def _pick_episodes(series: pd.Series, n: int, gap: pd.Timedelta, ascending: bool) -> list:
    """Pick the n most extreme dates that are at least `gap` apart (non-overlapping events)."""
    picked = []
    for d, v in series.sort_values(ascending=ascending).items():
        if np.isnan(v):
            continue
        if all(abs(d - p) >= gap for p, _ in picked):
            picked.append((d, v))
        if len(picked) == n:
            break
    return picked


def worst_droughts(dro: pd.DataFrame, n: int = 3) -> pd.DataFrame:
    """Region-wide: months where the mean % of normal across assessed counties is lowest."""
    a = dro.dropna(subset=["pct_of_normal"])
    reg = a.groupby("date").agg(mean_pct=("pct_of_normal", "mean"), n_assessed=("county", "size"),
                                n_warning_plus=("level", lambda s: s.isin(["Warning", "Emergency"]).sum()))
    reg = reg[reg["n_assessed"] >= max(3, len(C.COUNTIES) // 3)]
    rows = []
    for d, v in _pick_episodes(reg["mean_pct"], n, pd.Timedelta(days=270), ascending=True):
        worst = a[a["date"] == d].nsmallest(4, "pct_of_normal")
        rows.append({"rank": len(rows) + 1, "window_end": d.strftime("%Y-%m"),
                     "window": f"{(d - pd.DateOffset(months=2)).strftime('%b %Y')} - {d.strftime('%b %Y')}",
                     "regional_mean_pct_of_normal": round(v, 1),
                     "counties_warning_or_worse": int(reg.loc[d, "n_warning_plus"]),
                     "driest_counties": ", ".join(f"{r.county} ({r.pct_of_normal:.0f}%)" for r in worst.itertuples())})
    return pd.DataFrame(rows)


def worst_heavy_rain(hr: pd.DataFrame, n: int = 3) -> pd.DataFrame:
    """Region-wide: dates where the sum over counties of (3-day total / own p99) above 1 is largest."""
    x = hr.copy()
    x["excess"] = (x["ratio_to_p99"] - 1).clip(lower=0)
    reg = x.groupby("date").agg(score=("excess", "sum"),
                                n_over_p99=("ratio_to_p99", lambda s: int((s >= 1).sum())))
    rows = []
    for d, v in _pick_episodes(reg["score"], n, pd.Timedelta(days=45), ascending=False):
        top = x[x["date"] == d].nlargest(4, "ratio_to_p99")
        rows.append({"rank": len(rows) + 1, "date": d.strftime("%Y-%m-%d"),
                     "counties_over_p99": int(reg.loc[d, "n_over_p99"]),
                     "wettest_counties": ", ".join(f"{r.county} ({r.rain_3d_mm:.0f} mm, {r.ratio_to_p99:.2f}x p99)"
                                                   for r in top.itertuples())})
    return pd.DataFrame(rows)


def per_county_worst(dro: pd.DataFrame, hr: pd.DataFrame, n: int = 3) -> pd.DataFrame:
    rows = []
    for county in sorted(dro["county"].unique()):
        d = dro[dro["county"] == county].set_index("date")["pct_of_normal"]
        for dd, v in _pick_episodes(d, n, pd.Timedelta(days=270), ascending=True):
            rows.append({"county": county, "hazard": "drought", "when": dd.strftime("%Y-%m"),
                         "value": f"{v:.0f}% of normal (3-month)"})
        h = hr[hr["county"] == county].set_index("date")["rain_3d_mm"]
        for dd, v in _pick_episodes(h, n, pd.Timedelta(days=45), ascending=False):
            rows.append({"county": county, "hazard": "heavy rain", "when": dd.strftime("%Y-%m-%d"),
                         "value": f"{v:.0f} mm in 3 days"})
    return pd.DataFrame(rows)


def validate_events(dro: pd.DataFrame, hr: pd.DataFrame,
                    events: list[dict] | None = None) -> pd.DataFrame:
    """For each documented event and listed county: did our indicator reach Warning or worse
    inside the reported window (+/- 1 month)? Returns one row per event-county."""
    events = events if events is not None else C.REFERENCE_EVENTS
    rows = []
    for ev in events:
        s = pd.Timestamp(ev["start"]) - pd.DateOffset(months=1)
        e = pd.Timestamp(ev["end"]) + pd.DateOffset(months=1)
        for county in ev["counties"]:
            if county not in C.COUNTY_NAMES:
                continue
            if ev["hazard"] == "drought":
                w = dro[(dro["county"] == county) & dro["date"].between(s, e)]
                if w.empty or w["pct_of_normal"].isna().all():
                    status, best = "no data", None
                else:
                    best = w["pct_of_normal"].min()
                    status = "matched" if best < 50 else ("partial (Watch only)" if best < 75 else "missed")
                detail = None if best is None else f"lowest {best:.0f}% of normal"
            else:
                w = hr[(hr["county"] == county) & hr["date"].between(s, e)]
                if w.empty:
                    status, best = "no data", None
                else:
                    best = w["ratio_to_p99"].max()
                    p95_hit = (w["level"] != "Normal").any()
                    status = "matched" if best >= 1 else ("partial (Watch only)" if p95_hit else "missed")
                detail = None if best is None else f"max 3-day = {best:.2f}x own p99"
            rows.append({"event": ev["id"], "hazard": ev["hazard"], "county": county,
                         "window": f"{ev['start']} to {ev['end']}", "result": status,
                         "indicator_detail": detail, "source": ev["source"], "url": ev["url"]})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- heat
def heat_thresholds(daily: pd.DataFrame) -> pd.Series:
    base = daily[daily["date"].dt.year.between(C.NORMAL_START, C.NORMAL_END)]
    return base.groupby("county")["atmax"].quantile(C.HEAT_PCTL / 100)
