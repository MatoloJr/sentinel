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
    same 3 calendar months.

    * Windows whose normal is below DRY_SEASON_MIN_MM are dry season: a % of a tiny normal is
      noise, so they are 'Not assessed' instead of a false alarm.
    * Windows that normally bring less than MINOR_SEASON_SHARE_PCT of the year's rain are a minor
      season: the level is capped at Watch (`minor_season` = True, `uncapped_level` keeps the raw class).
    """
    out = []
    for county, g in mon.groupby("county"):
        g = g.sort_values("date").set_index("date")
        g = g.asfreq("MS")  # expose gaps so the 3-month window never spans a hole
        r3 = g["precip"].rolling(3, min_periods=3).sum()
        df = pd.DataFrame({"county": county, "rain_3m_mm": r3})
        df["month"] = df.index.month
        base = df[(df.index.year >= C.NORMAL_START) & (df.index.year <= C.NORMAL_END)]
        normal = base.groupby("month")["rain_3m_mm"].mean()
        annual = normal.sum() / 3 if len(normal) == 12 else np.nan  # each month sits in 3 windows
        df["normal_3m_mm"] = df["month"].map(normal)
        df["season_share_pct"] = 100 * df["normal_3m_mm"] / annual
        df["pct_of_normal"] = 100 * df["rain_3m_mm"] / df["normal_3m_mm"]
        dry = df["normal_3m_mm"] < C.DRY_SEASON_MIN_MM
        df.loc[dry, "pct_of_normal"] = np.nan
        df["uncapped_level"] = df["pct_of_normal"].map(drought_level)
        df["minor_season"] = (~dry) & (df["season_share_pct"] < C.MINOR_SEASON_SHARE_PCT)
        df["level"] = df["uncapped_level"]
        capped = df["minor_season"] & df["level"].isin(["Warning", "Emergency"])
        df.loc[capped, "level"] = "Watch"
        df.loc[dry, ["level", "uncapped_level"]] = "Dry season (not assessed)"
        out.append(df.dropna(subset=["rain_3m_mm"]).reset_index())
    return pd.concat(out, ignore_index=True)


def main_season(dro: pd.DataFrame) -> pd.DataFrame:
    """Assessed windows outside the minor season: the ones used to rank and validate droughts."""
    keep = dro["pct_of_normal"].notna()
    if "minor_season" in dro:
        keep &= ~dro["minor_season"].astype(bool)
    return dro[keep]


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
    """Region-wide: months where the mean % of normal across assessed main-season counties is lowest.
    Minor-season windows are left out: a % of a small normal ranks dry-season noise as 'drought'."""
    a = main_season(dro)
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
        d = main_season(dro[dro["county"] == county]).set_index("date")["pct_of_normal"]
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
                allw = dro[(dro["county"] == county) & dro["date"].between(s, e)]
                w = main_season(allw)
                minor = allw[allw["pct_of_normal"].notna() & ~allw.index.isin(w.index)]
                if allw.empty or allw["pct_of_normal"].isna().all():
                    status, best = "no data", None
                elif len(w) and w["pct_of_normal"].min() < 75:
                    best = w["pct_of_normal"].min()
                    status = "matched" if best < 50 else "partial (Watch only)"
                elif len(minor) and minor["pct_of_normal"].min() < 75:
                    best = minor["pct_of_normal"].min()
                    status = "partial (minor season only)"
                else:
                    best = (w if len(w) else allw)["pct_of_normal"].min()
                    status = "missed"
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


# ---------------------------------------------------------------- compound: drought-to-flood whiplash
def antecedent_dryness(mon: pd.DataFrame, months: int | None = None) -> pd.DataFrame:
    """Rain over the `months` full months BEFORE each month, as % of the 1991-2020 normal for the
    same window. Row `date` = month M uses months M-12 .. M-1, so it is known on day 1 of month M."""
    months = months or C.WHIPLASH_ANTECEDENT_MONTHS
    out = []
    for county, g in mon.groupby("county"):
        g = g.sort_values("date").set_index("date").asfreq("MS")
        # one extra month so the current (incomplete) month also gets its antecedent window
        g = g.reindex(pd.date_range(g.index.min(), g.index.max() + pd.offsets.MonthBegin(1), freq="MS", name="date"))
        prev = g["precip"].rolling(months, min_periods=months).sum().shift(1)
        df = pd.DataFrame({"county": county, "ante_mm": prev})
        df["month"] = df.index.month
        base = df[(df.index.year >= C.NORMAL_START) & (df.index.year <= C.NORMAL_END)]
        normal = base.groupby("month")["ante_mm"].mean()
        df["ante_normal_mm"] = df["month"].map(normal)
        df["ante_pct"] = 100 * df["ante_mm"] / df["ante_normal_mm"]
        df["ante_deficit_mm"] = (df["ante_normal_mm"] - df["ante_mm"]).clip(lower=0)
        out.append(df.dropna(subset=["ante_mm"]).drop(columns="month").reset_index())
    return pd.concat(out, ignore_index=True)


def whiplash_level(rain_level: str | None, ante_pct: float | None) -> str:
    """Compound level: heavy-rain level (Watch = p95, Warning = p99, Emergency = p99.9) when the
    preceding 12 months were at or below WHIPLASH_DRY_PCT of normal; otherwise Normal."""
    if rain_level not in ("Watch", "Warning", "Emergency"):
        return "Normal"
    if ante_pct is None or (isinstance(ante_pct, float) and np.isnan(ante_pct)) or ante_pct > C.WHIPLASH_DRY_PCT:
        return "Normal"
    return rain_level


def whiplash_indicator(hr: pd.DataFrame, ante: pd.DataFrame) -> pd.DataFrame:
    """Daily heavy-rain rows joined with the antecedent dryness of their month."""
    x = hr[["county", "date", "rain_3d_mm", "ratio_to_p99", "level"]].copy()
    x["month"] = x["date"].dt.to_period("M").dt.to_timestamp()
    a = ante.rename(columns={"date": "month"})
    x = x.merge(a, on=["county", "month"], how="left")
    x["whiplash_level"] = [whiplash_level(lv, ap) for lv, ap in zip(x["level"], x["ante_pct"])]
    return x.drop(columns="month")


def whiplash_episodes(wh: pd.DataFrame) -> pd.DataFrame:
    """One row per whiplash episode (whiplash days per county less than WHIPLASH_EPISODE_GAP_DAYS apart)."""
    hits = wh[wh["whiplash_level"] != "Normal"].sort_values(["county", "date"])
    rows = []
    gap = pd.Timedelta(days=C.WHIPLASH_EPISODE_GAP_DAYS)
    for county, g in hits.groupby("county"):
        prev = None
        block: list = []
        for r in g.itertuples():
            if prev is not None and r.date - prev > gap:
                rows.append(_episode(county, block))
                block = []
            block.append(r)
            prev = r.date
        if block:
            rows.append(_episode(county, block))
    cols = ["county", "start", "end", "level", "peak_date", "peak_3day_mm", "peak_ratio_to_p99",
            "antecedent_12m_pct", "antecedent_deficit_mm"]
    return pd.DataFrame(rows, columns=cols).sort_values(["start", "county"]).reset_index(drop=True)


def _episode(county: str, block: list) -> dict:
    peak = max(block, key=lambda r: r.rain_3d_mm)
    lvl = max((r.whiplash_level for r in block), key=lambda v: C.LEVEL_RANK.get(v, -1))
    first = block[0]
    return {"county": county, "start": first.date.strftime("%Y-%m-%d"), "end": block[-1].date.strftime("%Y-%m-%d"),
            "level": lvl, "peak_date": peak.date.strftime("%Y-%m-%d"), "peak_3day_mm": round(float(peak.rain_3d_mm), 1),
            "peak_ratio_to_p99": round(float(peak.ratio_to_p99), 2),
            "antecedent_12m_pct": round(float(first.ante_pct), 0),
            "antecedent_deficit_mm": round(float(first.ante_deficit_mm), 0)}


def whiplash_summary(wh: pd.DataFrame, episodes: pd.DataFrame) -> pd.DataFrame:
    """Per county: how many p99 heavy-rain days fell on drought-hit land, and episode counts."""
    rows = []
    for county, g in wh.groupby("county"):
        heavy = g[g["level"].isin(["Warning", "Emergency"])]
        on_dry = heavy[heavy["whiplash_level"] != "Normal"]
        ep = episodes[episodes["county"] == county]
        years = g["date"].dt.year.nunique()
        rows.append({"county": county,
                     "p99_rain_days": len(heavy),
                     "p99_rain_days_on_drought_land": len(on_dry),
                     "share_on_drought_land_pct": round(100 * len(on_dry) / len(heavy), 0) if len(heavy) else None,
                     "episodes_warning_plus": int(ep["level"].isin(["Warning", "Emergency"]).sum()),
                     "episodes_any": len(ep),
                     "episodes_per_decade": round(10 * len(ep) / years, 1) if years else None,
                     "last_episode": ep["start"].max() if len(ep) else None})
    return pd.DataFrame(rows)


def whiplash_stats(wh: pd.DataFrame, episodes: pd.DataFrame, dro: pd.DataFrame) -> dict:
    """Region-wide numbers for the evidence page, incl. the single-hazard blind spot: in how many
    episodes did the standard 3-month drought indicator already say 'Normal' when the rain hit?"""
    e = episodes.copy()
    years = wh["date"].dt.year.nunique() or 1
    n_c = wh["county"].nunique() or 1
    out = {"episodes": int(len(e)), "episodes_warning_plus": int(e["level"].isin(["Warning", "Emergency"]).sum()),
           "episodes_per_county_decade": round(10 * len(e) / n_c / years, 1),
           "warning_plus_per_county_decade": float(round(10 * e["level"].isin(["Warning", "Emergency"]).sum() / n_c / years, 1))}
    heavy = wh[wh["level"].isin(["Warning", "Emergency"])]
    out["p99_rain_days"] = int(len(heavy))
    out["p99_rain_days_on_drought_land_pct"] = (float(round(100 * (heavy["whiplash_level"] != "Normal").mean(), 0))
                                                 if len(heavy) else None)
    out["blind_spot_drought_indicator_normal_pct"] = None
    out["blind_spot_drought_indicator_below_warning_pct"] = None
    if len(e):
        e["m"] = pd.to_datetime(e["start"]).dt.to_period("M").dt.to_timestamp()
        j = e.merge(dro[["county", "date", "level"]].rename(columns={"date": "m", "level": "drought_level"}),
                    on=["county", "m"], how="left")
        quiet = j["drought_level"].isin(["Normal", "Dry season (not assessed)"])
        below_warning = quiet | (j["drought_level"] == "Watch")
        out["blind_spot_drought_indicator_normal_pct"] = float(round(100 * quiet.mean(), 0))
        out["blind_spot_drought_indicator_below_warning_pct"] = float(round(100 * below_warning.mean(), 0))
    return out


def whiplash_sensitivity(hr: pd.DataFrame, mon: pd.DataFrame,
                         months_list=(6, 12), dry_list=(60, 75, 90)) -> pd.DataFrame:
    """How the validation result and alert rate change with the rule's two settings. The published
    rule (12 months, 75%) was fixed before validation; this table shows it was not tuned to the events."""
    rows = []
    keep = C.WHIPLASH_DRY_PCT
    try:
        for m in months_list:
            ante = antecedent_dryness(mon, m)
            for dry in dry_list:
                C.WHIPLASH_DRY_PCT = float(dry)
                wh = whiplash_indicator(hr, ante)
                v = validate_whiplash(wh)
                ep = whiplash_episodes(wh)
                years = wh["date"].dt.year.nunique() or 1
                n_c = wh["county"].nunique() or 1
                rows.append({"antecedent_months": m, "dry_pct": dry,
                             "matched": int((v["result"] == "matched").sum()),
                             "partial": int(v["result"].str.startswith("partial").sum()), "county_events": len(v),
                             "episodes_per_county_decade": round(10 * len(ep) / n_c / years, 1),
                             "published_rule": m == C.WHIPLASH_ANTECEDENT_MONTHS and float(dry) == keep})
    finally:
        C.WHIPLASH_DRY_PCT = keep
    return pd.DataFrame(rows)


def validate_whiplash(wh: pd.DataFrame, events: list[dict] | None = None) -> pd.DataFrame:
    """Documented rain-after-drought disasters: did the compound indicator fire in the window (+/- 1 month)?
    matched = whiplash Warning+, partial = whiplash Watch; misses say which half was missing."""
    events = events if events is not None else C.WHIPLASH_EVENTS
    rows = []
    for ev in events:
        s = pd.Timestamp(ev["start"]) - pd.DateOffset(months=1)
        e = pd.Timestamp(ev["end"]) + pd.DateOffset(months=1)
        for county in ev["counties"]:
            if county not in C.COUNTY_NAMES:
                continue
            w = wh[(wh["county"] == county) & wh["date"].between(s, e)]
            if w.empty:
                status, detail = "no data", None
            else:
                best = max(w["whiplash_level"], key=lambda v: C.LEVEL_RANK.get(v, -1))
                ante = w["ante_pct"].min()
                rain = w["ratio_to_p99"].max()
                if C.LEVEL_RANK.get(best, 0) >= 2:
                    status = "matched"
                elif best == "Watch":
                    status = "partial (Watch only)"
                elif (w["level"] != "Normal").any():
                    status = "missed (heavy rain, but prior 12 months not dry enough)"
                else:
                    status = "missed (no heavy rain at the HQ point)"
                detail = f"prior 12 months {ante:.0f}% of normal; max 3-day = {rain:.2f}x own p99"
            rows.append({"event": ev["id"], "hazard": "whiplash", "county": county,
                         "window": f"{ev['start']} to {ev['end']}", "result": status,
                         "indicator_detail": detail, "source": ev["source"], "url": ev["url"]})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- heat
def heat_thresholds(daily: pd.DataFrame) -> pd.Series:
    base = daily[daily["date"].dt.year.between(C.NORMAL_START, C.NORMAL_END)]
    return base.groupby("county")["atmax"].quantile(C.HEAT_PCTL / 100)
