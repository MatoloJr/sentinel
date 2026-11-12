"""SYNTHETIC test fixture - used only by the test-suite to exercise the pipeline offline.

Nothing here is real data and nothing here is ever written to data/ or outputs/.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from sentinel import config as C


def make_raw(raw: Path, seed: int = 1, end: str = "2026-11-01") -> None:
    rng = np.random.default_rng(seed)
    raw.mkdir(parents=True, exist_ok=True)
    dates = pd.date_range("1991-01-01", end, freq="D")
    months = pd.date_range("1990-01-01", end, freq="MS")
    # climate drivers: an AR(1) "ONI" and "DMI" that genuinely modulate OND rain below
    oni = np.zeros(len(months)); dmi = np.zeros(len(months))
    for i in range(1, len(months)):
        oni[i] = 0.9 * oni[i - 1] + rng.normal(0, 0.3)
        dmi[i] = 0.8 * dmi[i - 1] + rng.normal(0, 0.25)
    idx = pd.DataFrame({"date": months, "oni": oni.round(2), "dmi": dmi.round(3)})
    idx.loc[idx.index[-3:], "dmi"] = np.nan  # mimic publication lag
    idx.to_parquet(raw / "climate_indices.parquet", index=False)
    dmi_by_month = dict(zip(months, dmi))

    frames = []
    doy = dates.day_of_year.to_numpy()
    for k, c in enumerate(C.COUNTIES):
        wet = 0.25 + 0.2 * np.sin(2 * np.pi * (doy - 60) / 182.5) ** 2  # bimodal-ish
        mstart = dates.to_period("M").to_timestamp()
        mod = np.array([dmi_by_month.get(m - pd.DateOffset(months=1), 0.0) for m in mstart])
        ond = np.isin(dates.month, [10, 11, 12])
        wet = np.clip(wet + 0.25 * ond * mod, 0.02, 0.95)
        rain = (rng.random(len(dates)) < wet) * rng.gamma(0.8, 8 + k, len(dates))
        tmax = 30 + 3 * np.sin(2 * np.pi * doy / 365) + 0.02 * (dates.year - 1991) + rng.normal(0, 1.2, len(dates))
        frames.append(pd.DataFrame({
            "county": c.name, "date": dates, "precip": rain.round(1), "tmax": tmax,
            "tmin": tmax - 10, "tmean": tmax - 5, "atmax": tmax + 2, "grid_lat": c.lat, "grid_lon": c.lon}))
    pd.concat(frames).to_parquet(raw / "daily_all.parquet", index=False)

    # county polygons: small squares around each HQ point (fake geography)
    feats = []
    for c in C.COUNTIES:
        h = 0.08
        ring = [[c.lon - h, c.lat - h], [c.lon + h, c.lat - h], [c.lon + h, c.lat + h],
                [c.lon - h, c.lat + h], [c.lon - h, c.lat - h]]
        feats.append({"type": "Feature", "properties": {"shapeName": c.name},
                      "geometry": {"type": "Polygon", "coordinates": [ring]}})
    (raw / "kenya_adm1.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}))

    import rasterio
    from rasterio.transform import from_origin
    arr = np.full((140, 120), 50.0, dtype="float32")  # 0.1 deg cells over 33.5-45.5E, 5N-9S
    with rasterio.open(raw / "ken_ppp_2020_1km_UNadj.tif", "w", driver="GTiff", height=140, width=120,
                       count=1, dtype="float32", crs="EPSG:4326", nodata=-99999,
                       transform=from_origin(33.5, 5.0, 0.1, 0.1)) as dst:
        dst.write(arr, 1)

    # three fake storms: one passes ~150 km off Lamu, two stay far south
    rows = []
    for sid, season, lat0, lon0 in [("S1", 1994, -1.5, 43.0), ("S2", 2008, -12.0, 45.0), ("S3", 2019, -15.0, 41.0)]:
        for i in range(10):
            rows.append({"SID": sid, "SEASON": season, "BASIN": "SI", "NAME": f"FAKE{sid}",
                         "ISO_TIME": pd.Timestamp(season, 1, 1) + pd.Timedelta(hours=6 * i), "NATURE": "TS",
                         "LAT": lat0 - 0.3 * i, "LON": lon0 - 0.1 * i, "WMO_WIND": 40.0, "USA_WIND": np.nan,
                         "TRACK_TYPE": "main"})
    pd.DataFrame(rows).to_parquet(raw / "ibtracs_si_ni.parquet", index=False)

    fdates = pd.date_range(pd.Timestamp(end), periods=7, freq="D")
    fc = []
    for k, c in enumerate(C.COUNTIES):
        fc.append(pd.DataFrame({"county": c.name, "date": fdates,
                                "precip_sum": [0, 5, 80 if k == 5 else 3, 90 if k == 5 else 2, 4, 0, 1],
                                "wind_speed_10m_max": 20.0, "wind_gusts_10m_max": 70.0 if c.coastal else 30.0,
                                "temperature_2m_max": 31.0, "apparent_temperature_max": 33.0,
                                "fetched_utc": "2026-11-01T06:00"}))
    pd.concat(fc).to_parquet(raw / "forecast_latest.parquet", index=False)
