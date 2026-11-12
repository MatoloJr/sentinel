"""Short-range watch: flag counties whose forecast 3-day rain passes their own p99 (and p95/p99.9)."""
from __future__ import annotations

import pandas as pd

from . import config as C
from .indicators import heavy_level


def forecast_watch(fc: pd.DataFrame, thr: pd.DataFrame, heat_thr: pd.Series | None = None) -> pd.DataFrame:
    rows = []
    if "precip_sum" not in fc and "precipitation_sum" in fc:  # raw Open-Meteo column name
        fc = fc.rename(columns={"precipitation_sum": "precip_sum"})
    for county, g in fc.groupby("county"):
        g = g.sort_values("date").reset_index(drop=True)
        r3 = g["precip_sum"].rolling(3, min_periods=3).sum()
        i = int(r3.idxmax()) if r3.notna().any() else None
        max3 = float(r3.max()) if i is not None else float("nan")
        t = thr.loc[county]
        coastal = C.COUNTY_BY_NAME[county].coastal
        gust = float(g["wind_gusts_10m_max"].max()) if "wind_gusts_10m_max" in g else float("nan")
        row = {
            "county": county,
            "forecast_from": f"{g['date'].min():%Y-%m-%d}", "forecast_to": f"{g['date'].max():%Y-%m-%d}",
            "forecast_7day_total_mm": round(float(g["precip_sum"].sum()), 1),
            "max_3day_total_mm": round(max3, 1),
            "max_3day_window": (f"{g.loc[i - 2, 'date']:%d %b} - {g.loc[i, 'date']:%d %b}" if i is not None else None),
            "p95_3day_mm": round(float(t["p95_3day_mm"]), 1), "p99_3day_mm": round(float(t["p99_3day_mm"]), 1),
            "p99.9_3day_mm": round(float(t["p99.9_3day_mm"]), 1),
            "heavy_rain_level": heavy_level(max3, t),
            "exceeds_p99": bool(max3 >= t["p99_3day_mm"]),
            "max_gust_kmh": round(gust, 0) if coastal else None,
            "gale_gust_flag": bool(gust >= C.GALE_GUST_KMH) if coastal else None,
            "fetched_utc": g["fetched_utc"].iloc[0] if "fetched_utc" in g else None,
        }
        if heat_thr is not None and "apparent_temperature_max" in g:
            hot = int((g["apparent_temperature_max"] > heat_thr[county]).sum())
            row["hot_days_forecast"] = hot
            row["heat_threshold_c"] = round(float(heat_thr[county]), 1)
        rows.append(row)
    return pd.DataFrame(rows)
