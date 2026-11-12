"""One command to rebuild everything: python run_all.py

1. download + cache raw data (skip with --offline)
2. weather behaviour, indicators, validation, cyclone + population exposure
3. seasonal outlook backtest + live outlook
4. 7-day forecast watch
5. current status table used by the dashboard and the agent
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

import pandas as pd

from sentinel import climate, config as C, geo, indicators as ind, outlook, watch


def exposure_class(per_decade: float) -> str:
    if per_decade <= 0:
        return "None recorded"
    if per_decade < 1:
        return "Low"
    if per_decade < 3:
        return "Moderate"
    return "High"


def build(offline: bool, skip_forecast: bool, n_boot: int) -> dict:
    C.ensure_dirs()
    if not offline:
        from sentinel import fetch
        fetch.fetch_all(skip_forecast=skip_forecast)
    raw, out = C.RAW_DIR, C.OUT_DIR
    summary: dict = {"built_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}

    print("== weather behaviour")
    daily = pd.read_parquet(raw / "daily_all.parquet")
    daily["date"] = pd.to_datetime(daily["date"])
    summary["daily_range"] = [str(daily["date"].min().date()), str(daily["date"].max().date())]
    mon = climate.monthly(daily)
    mon.to_parquet(out / "monthly.parquet", index=False)
    clim = climate.climatology(mon)
    clim.to_csv(out / "climatology.csv", index=False)
    climate.rainy_seasons(clim).to_csv(out / "seasons.csv", index=False)
    climate.trends(daily).to_csv(out / "trends.csv", index=False)
    ext = climate.yearly_extremes(daily)
    ext.to_csv(out / "extremes.csv", index=False)
    climate.extremes_trends(ext).to_csv(out / "extremes_trends.csv", index=False)

    print("== hazard indicators + validation")
    dro = ind.drought_indicator(mon)
    dro.to_parquet(out / "drought.parquet", index=False)
    ind.drought_class_frequency(dro).to_csv(out / "drought_class_frequency.csv")
    thr = ind.heavy_thresholds(daily)
    thr.to_csv(out / "heavy_thresholds.csv")
    hr = ind.heavy_rain_indicator(daily, thr)
    hr.to_parquet(out / "heavy_rain.parquet", index=False)
    heat_thr = ind.heat_thresholds(daily)
    heat_thr.rename("heat_threshold_c").to_csv(out / "heat_thresholds.csv")
    ind.worst_droughts(dro).to_csv(out / "worst_droughts.csv", index=False)
    ind.worst_heavy_rain(hr).to_csv(out / "worst_heavy_rain.csv", index=False)
    ind.per_county_worst(dro, hr).to_csv(out / "per_county_worst.csv", index=False)
    ind.validate_events(dro, hr).to_csv(out / "validation.csv", index=False)

    print("== geography, population, cyclones")
    counties = geo.load_counties(raw / "kenya_adm1.geojson")
    pop = geo.population_by_county(counties, raw / "ken_ppp_2020_1km_UNadj.tif")
    pop.round(1).to_csv(out / "population.csv", index=False)
    ib = pd.read_parquet(raw / "ibtracs_si_ni.parquet")
    cyc = geo.cyclone_exposure(ib, counties)
    cyc["ranking"]["exposure_class"] = cyc["ranking"]["storms_per_decade"].map(exposure_class)
    cyc["ranking"].round(2).to_csv(out / "cyclone_ranking.csv", index=False)
    cyc["per_decade"].round(3).to_csv(out / "cyclone_per_decade.csv", index=False)
    cyc["per_season"].to_csv(out / "cyclone_per_season.csv", index=False)
    cyc["tracks"].to_parquet(out / "cyclone_tracks.parquet", index=False)

    print("== seasonal outlook")
    idx = pd.read_parquet(raw / "climate_indices.parquet")
    idx["date"] = pd.to_datetime(idx["date"])
    res = outlook.run(mon, idx, n_boot=n_boot)
    outlook.save(res, out)
    summary["outlook"] = res["info"]

    print("== 7-day watch")
    fc_path = raw / "forecast_latest.parquet"
    if fc_path.exists():
        fc = pd.read_parquet(fc_path)
        w = watch.forecast_watch(fc, thr, heat_thr)
        w.to_csv(out / "watch.csv", index=False)
        summary["forecast_fetched_utc"] = str(fc["fetched_utc"].iloc[0])
    else:
        w = None
        summary["forecast_fetched_utc"] = None
        (out / "watch.csv").unlink(missing_ok=True)

    print("== current status")
    status = current_status(dro, hr, w, cyc["ranking"], pop, res["live"])
    status.to_csv(out / "status.csv", index=False)
    for col in ("drought_level", "observed_heavy_level", "forecast_heavy_level", "cyclone_exposure_class"):
        if col in status and status[col].notna().any():
            geo.people_by_level(status, pop, col).to_csv(out / f"people_by_{col}.csv", index=False)
    gj = counties.merge(status, on="county", how="left")
    gj.to_file(out / "counties_status.geojson", driver="GeoJSON")
    summary["latest_complete_month"] = str(mon["date"].max().date())
    (out / "run_summary.json").write_text(json.dumps(summary, indent=2, default=str))
    print(f"Done. Outputs in {out}")
    return summary


def current_status(dro, hr, w, cyc_rank, pop, live) -> pd.DataFrame:
    rows = []
    for name in C.COUNTY_NAMES:
        d = dro[dro["county"] == name].sort_values("date").iloc[-1]
        h = hr[hr["county"] == name].sort_values("date")
        last7 = h[h["date"] > h["date"].max() - pd.Timedelta(days=7)]
        hi = last7.loc[last7["rain_3d_mm"].idxmax()]
        lvl = max(last7["level"], key=lambda x: C.LEVEL_RANK.get(x, -1))
        cr = cyc_rank.set_index("county").loc[name]
        lv = live.set_index("county").loc[name] if name in set(live["county"]) else None
        row = {
            "county": name, "zone": C.COUNTY_BY_NAME[name].zone,
            "drought_window_end": f"{d['date']:%Y-%m}",
            "rain_3m_mm": round(float(d["rain_3m_mm"]), 1), "normal_3m_mm": round(float(d["normal_3m_mm"]), 1),
            "pct_of_normal": None if pd.isna(d["pct_of_normal"]) else round(float(d["pct_of_normal"]), 0),
            "drought_level": d["level"],
            "observed_to": f"{h['date'].max():%Y-%m-%d}",
            "observed_max_3day_mm_last7d": round(float(hi["rain_3d_mm"]), 1),
            "observed_ratio_to_p99": round(float(hi["ratio_to_p99"]), 2),
            "observed_heavy_level": lvl,
            "cyclone_storms_300km": int(cr["tropical_storms_300km"]),
            "cyclone_exposure_class": cr["exposure_class"], "cyclone_rank": int(cr["exposure_rank"]),
            "population_2020": round(float(pop.set_index("county").loc[name, "population_2020"])),
            "outlook_prob_below": None if lv is None else lv["prob_below_normal"],
            "outlook_basis": None if lv is None else lv["basis"],
        }
        if w is not None and name in set(w["county"]):
            wr = w.set_index("county").loc[name]
            row.update({"forecast_max_3day_mm": wr["max_3day_total_mm"], "forecast_heavy_level": wr["heavy_rain_level"],
                        "forecast_exceeds_p99": bool(wr["exceeds_p99"])})
        else:
            row.update({"forecast_max_3day_mm": None, "forecast_heavy_level": None, "forecast_exceeds_p99": None})
        rows.append(row)
    return pd.DataFrame(rows)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--offline", action="store_true", help="use cached raw data, no downloads")
    ap.add_argument("--skip-forecast", action="store_true", help="do not call the live forecast API")
    ap.add_argument("--data-dir", type=Path, help="override data directory (raw files in <dir>/raw)")
    ap.add_argument("--out-dir", type=Path, help="override outputs directory")
    ap.add_argument("--bootstrap", type=int, default=C.BOOTSTRAP_N)
    a = ap.parse_args()
    if a.data_dir:
        C.DATA_DIR, C.RAW_DIR = a.data_dir, a.data_dir / "raw"
    if a.out_dir:
        C.OUT_DIR = a.out_dir
    build(a.offline, a.skip_forecast, a.bootstrap)
