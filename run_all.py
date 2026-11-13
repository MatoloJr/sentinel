"""One command to rebuild everything: python run_all.py

1. download + cache raw data (skip with --offline)
2. weather behaviour, indicators, validation, cyclone + population exposure
3. seasonal outlook backtest + live outlook
4. 7-day forecast watch
5. drought-to-flood whiplash (compound hazard) history, validation and live status
6. current status table used by the dashboard and the agent
7. insights.json: ranked, actionable county cards (manager + public views)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

import pandas as pd

from sentinel import climate, config as C, geo, indicators as ind, insights, outlook, watch


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

    print("== compound: drought-to-flood whiplash")
    ante = ind.antecedent_dryness(mon)
    wh = ind.whiplash_indicator(hr, ante)
    episodes = ind.whiplash_episodes(wh)
    episodes.to_csv(out / "whiplash_episodes.csv", index=False)
    ind.whiplash_summary(wh, episodes).to_csv(out / "whiplash_summary.csv", index=False)
    wval = ind.validate_whiplash(wh)
    wval.to_csv(out / "whiplash_validation.csv", index=False)
    ind.whiplash_sensitivity(hr, mon).to_csv(out / "whiplash_sensitivity.csv", index=False)
    wstats = ind.whiplash_stats(wh, episodes, dro)
    (out / "whiplash_stats.json").write_text(json.dumps(wstats, indent=2))
    summary["whiplash"] = wstats
    pd.concat([ind.validate_events(dro, hr), wval], ignore_index=True).to_csv(out / "validation.csv", index=False)

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
    active, active_meta = load_active_storms(raw)
    summary["active_storm_check_utc"] = active_meta.get("fetched_utc")
    status = current_status(dro, hr, w, cyc["ranking"], pop, res["live"], ante, active, active_meta)
    status.to_csv(out / "status.csv", index=False)
    for col in ("drought_level", "observed_heavy_level", "forecast_heavy_level", "cyclone_exposure_class"):
        if col in status and status[col].notna().any():
            geo.people_by_level(status, pop, col).to_csv(out / f"people_by_{col}.csv", index=False)
    gj = counties.merge(status, on="county", how="left")
    gj.to_file(out / "counties_status.geojson", driver="GeoJSON")
    summary["latest_complete_month"] = str(mon["date"].max().date())
    (out / "run_summary.json").write_text(json.dumps(summary, indent=2, default=str))

    print("== insights + actions")
    insights.save(out)
    print(f"Done. Outputs in {out}")
    return summary


def load_active_storms(raw: Path) -> tuple[pd.DataFrame | None, dict]:
    """Cached IBTrACS ACTIVE list, or (None, {}) when it is missing or too old to trust."""
    f, m = raw / "ibtracs_active.parquet", raw / "ibtracs_active_meta.json"
    if not (f.exists() and m.exists()):
        return None, {}
    meta = json.loads(m.read_text())
    try:
        age = dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(meta["fetched_utc"])
    except (KeyError, ValueError):
        return None, {}
    meta["age_days"] = round(age.total_seconds() / 86400, 1)
    if age > dt.timedelta(days=C.ACTIVE_STORM_MAX_AGE_DAYS):
        return None, {**meta, "stale": True}
    return pd.read_parquet(f), meta


def current_status(dro, hr, w, cyc_rank, pop, live, ante=None, active=None, active_meta=None) -> pd.DataFrame:
    active_meta = active_meta or {}
    rows = []
    for name in C.COUNTY_NAMES:
        d = dro[dro["county"] == name].sort_values("date").iloc[-1]
        h = hr[hr["county"] == name].sort_values("date")
        last7 = h[h["date"] > h["date"].max() - pd.Timedelta(days=7)]
        hi = last7.loc[last7["rain_3d_mm"].idxmax()]
        lvl = max(last7["level"], key=lambda x: C.LEVEL_RANK.get(x, -1))
        cr = cyc_rank.set_index("county").loc[name]
        lv = live.set_index("county").loc[name] if name in set(live["county"]) else None
        cty = C.COUNTY_BY_NAME[name]
        row = {
            "county": name, "zone": cty.zone, "urban": cty.urban,
            "drought_window_end": f"{d['date']:%Y-%m}",
            "rain_3m_mm": round(float(d["rain_3m_mm"]), 1), "normal_3m_mm": round(float(d["normal_3m_mm"]), 1),
            "pct_of_normal": None if pd.isna(d["pct_of_normal"]) else round(float(d["pct_of_normal"]), 0),
            "drought_level": d["level"],
            "drought_minor_season": bool(d.get("minor_season", False)),
            "drought_uncapped_level": d.get("uncapped_level", d["level"]),
            "season_share_pct": None if pd.isna(d.get("season_share_pct")) else round(float(d["season_share_pct"]), 0),
            "observed_to": f"{h['date'].max():%Y-%m-%d}",
            "observed_max_3day_mm_last7d": round(float(hi["rain_3d_mm"]), 1),
            "observed_ratio_to_p99": round(float(hi["ratio_to_p99"]), 2),
            "observed_heavy_level": lvl,
            "cyclone_storms_300km": int(cr["tropical_storms_300km"]),
            "cyclone_exposure_class": cr["exposure_class"], "cyclone_rank": int(cr["exposure_rank"]),
            "population": round(float(pop.set_index("county").loc[name, "population"])),
            "population_source": pop.set_index("county").loc[name, "population_source"],
            "outlook_prob_below": None if lv is None else lv["prob_below_normal"],
            "outlook_basis": None if lv is None else lv["basis"],
        }
        # live active-storm proximity (coastal counties only; None = check unavailable)
        storm = geo.nearest_active_storm(active, cty.lat, cty.lon) if active is not None else {}
        row.update({"active_storm_check_utc": active_meta.get("fetched_utc") if active is not None else None,
                    "active_storm_name": storm.get("name"), "active_storm_km": storm.get("km")})
        # antecedent dryness for the current month (12 full months before it)
        a = ante[ante["county"] == name].sort_values("date") if ante is not None else None
        if a is not None and len(a):
            a = a.iloc[-1]
            row.update({"ante_12m_pct": round(float(a["ante_pct"]), 0), "ante_12m_mm": round(float(a["ante_mm"]), 1),
                        "ante_12m_normal_mm": round(float(a["ante_normal_mm"]), 1),
                        "ante_12m_deficit_mm": round(float(a["ante_deficit_mm"]), 1),
                        "ante_window_end": f"{a['date'] - pd.DateOffset(months=1):%Y-%m}"})
        else:
            row.update({"ante_12m_pct": None, "ante_12m_mm": None, "ante_12m_normal_mm": None,
                        "ante_12m_deficit_mm": None, "ante_window_end": None})
        if w is not None and name in set(w["county"]):
            wr = w.set_index("county").loc[name]
            row.update({"forecast_max_3day_mm": wr["max_3day_total_mm"], "forecast_heavy_level": wr["heavy_rain_level"],
                        "forecast_exceeds_p99": bool(wr["exceeds_p99"])})
        else:
            row.update({"forecast_max_3day_mm": None, "forecast_heavy_level": None, "forecast_exceeds_p99": None})
        # compound: heavy rain (observed last 7 days or forecast next 7) on drought-hit land
        fc_lvl = row.get("forecast_heavy_level") or "Normal"
        use_fc = C.LEVEL_RANK.get(fc_lvl, -1) >= C.LEVEL_RANK.get(lvl, -1)
        rain_lvl = fc_lvl if use_fc else lvl
        row["whiplash_level"] = ind.whiplash_level(rain_lvl, row["ante_12m_pct"])
        row["whiplash_trigger"] = None if row["whiplash_level"] == "Normal" else ("forecast" if use_fc else "observed")
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
