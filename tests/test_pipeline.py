import json

import numpy as np
import pandas as pd

from sentinel import config as C
from sentinel import indicators as ind


def test_outputs_exist(synth):
    for f in ["climatology.csv", "seasons.csv", "trends.csv", "extremes.csv", "validation.csv",
              "worst_droughts.csv", "worst_heavy_rain.csv", "cyclone_ranking.csv", "population.csv",
              "outlook_metrics.csv", "outlook_live.csv", "status.csv", "watch.csv", "counties_status.geojson"]:
        assert (C.OUT_DIR / f).exists(), f
    st = pd.read_csv(C.OUT_DIR / "status.csv")
    assert len(st) == len(C.COUNTIES)
    assert len(pd.read_csv(C.OUT_DIR / "worst_droughts.csv")) == 3
    assert len(pd.read_csv(C.OUT_DIR / "worst_heavy_rain.csv")) == 3


def test_drought_levels():
    assert ind.drought_level(80) == "Normal"
    assert ind.drought_level(60) == "Watch"
    assert ind.drought_level(30) == "Warning"
    assert ind.drought_level(10) == "Emergency"
    assert ind.drought_level(np.nan) == "Not assessed"


def test_dry_season_not_assessed(synth):
    d = pd.read_parquet(C.OUT_DIR / "drought.parquet")
    dry = d[d["normal_3m_mm"] < C.DRY_SEASON_MIN_MM]
    assert dry["pct_of_normal"].isna().all()


def test_heavy_rain_thresholds_ordered(synth):
    t = pd.read_csv(C.OUT_DIR / "heavy_thresholds.csv")
    assert (t["p95_3day_mm"] <= t["p99_3day_mm"]).all() and (t["p99_3day_mm"] <= t["p99.9_3day_mm"]).all()


def test_forecast_watch_flags_p99(synth):
    w = pd.read_csv(C.OUT_DIR / "watch.csv").set_index("county")
    # synthetic forecast puts 170 mm in 2 days over Tana River; every other county is dry
    assert bool(w.loc["Tana River", "exceeds_p99"])
    assert not w.drop("Tana River")["exceeds_p99"].any()
    assert w.loc["Mombasa", "gale_gust_flag"] and pd.isna(w.loc["Nairobi", "gale_gust_flag"])


def test_cyclone_uses_300km(synth):
    r = pd.read_csv(C.OUT_DIR / "cyclone_ranking.csv").set_index("county")
    assert r.loc["Lamu", "tropical_storms_300km"] == 1       # fake storm passes ~180 km away
    assert r.loc["Turkana", "tropical_storms_300km"] == 0
    assert (r["closest_approach_km"].dropna() <= C.CYCLONE_RADIUS_KM).all()


def test_population_check_columns(synth):
    p = pd.read_csv(C.OUT_DIR / "population.csv")
    assert {"population_2020", "census_2019", "worldpop_vs_census_pct"} <= set(p.columns)


def test_run_summary(synth):
    s = json.loads((C.OUT_DIR / "run_summary.json").read_text())
    assert s["outlook"]["split"]["test_start"] == "2018-01-01"
