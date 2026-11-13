"""Download and cache every raw dataset. Each fetch is idempotent: cached files are reused.

Run via `python run_all.py` (or `python -m sentinel.fetch`). Sources and licences are in DATA.md.
"""
from __future__ import annotations

import datetime as dt
import io
import json
import time
from pathlib import Path

import pandas as pd
import requests

from . import config as C

UA = {"User-Agent": "ClimateSentinel-hackathon/1.0 (education; planning-support prototype)"}
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
DAILY_VARS = [
    "precipitation_sum", "temperature_2m_max", "temperature_2m_min",
    "temperature_2m_mean", "apparent_temperature_max",
]
ONI_URL = "https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt"
DMI_URL = "https://psl.noaa.gov/gcos_wgsp/Timeseries/Data/dmi.had.long.data"
IBTRACS_URLS = [
    "https://www.ncei.noaa.gov/data/international-best-track-archive-for-climate-stewardship-ibtracs/v04r01/access/csv/ibtracs.{basin}.list.v04r01.csv",
]
GEOBOUNDARIES_API = "https://www.geoboundaries.org/api/current/gbOpen/KEN/ADM1/"
WORLDPOP_URL = (
    "https://data.worldpop.org/GIS/Population/Global_2000_2020_1km_UNadj/2020/KEN/"
    "ken_ppp_2020_1km_Aggregated_UNadj.tif"
)


class RateLimitError(RuntimeError):
    """Open-Meteo daily quota exhausted: retrying today is pointless."""


def _rate_limit_wait(reason: str) -> float | None:
    """Seconds to wait for an Open-Meteo 429, or None if the daily quota is gone.

    Open-Meteo's free tier has minutely / hourly / daily limits and the 429 body says
    which one was hit. Short exponential backoff can never clear an hourly limit.
    """
    low = reason.lower()
    if "daily" in low:
        return None
    if "hourly" in low:
        now = dt.datetime.now()
        nxt = (now + dt.timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        return (nxt - now).total_seconds() + 30
    return 65.0  # minutely (or unspecified)


def _get(url: str, params: dict | None = None, *, tries: int = 6, timeout: int = 120,
         stream: bool = False) -> requests.Response:
    """GET with backoff. Network errors back off exponentially; Open-Meteo 429s wait
    for the specific quota window (minute / hour) to reset and don't use up retries."""
    wait = 5.0
    last: object = None
    attempt = 0
    rate_waits = 0
    while attempt < tries:
        try:
            r = requests.get(url, params=params, headers=UA, timeout=timeout, stream=stream)
        except requests.RequestException as e:  # network hiccup
            last = e
            attempt += 1
            print(f"  attempt {attempt} failed: {e}; retry in {wait:.0f}s")
            time.sleep(wait)
            wait = min(wait * 2, 900)
            continue
        if r.status_code == 429:
            reason = r.text[:200]
            last = f"HTTP 429 {reason}"
            pause = _rate_limit_wait(reason)
            rate_waits += 1
            if pause is None or rate_waits > 8:
                raise RateLimitError(
                    f"Open-Meteo quota exhausted ({reason}). Progress is cached; "
                    "re-run `python run_all.py` later (tomorrow for the daily limit) to resume.")
            until = (dt.datetime.now() + dt.timedelta(seconds=pause)).strftime("%H:%M")
            print(f"  rate limited ({reason}); waiting {pause:.0f}s (until ~{until})")
            time.sleep(pause)
            continue
        try:
            r.raise_for_status()
        except requests.HTTPError as e:
            last = e
            attempt += 1
            print(f"  attempt {attempt} failed: {e}; retry in {wait:.0f}s")
            time.sleep(wait)
            wait = min(wait * 2, 900)
            continue
        return r
    raise RuntimeError(f"Could not download {url}: {last}")


def _access_log(name: str, url: str) -> None:
    """Append source + access date to data/raw/ACCESS_LOG.json (copied into DATA.md tables)."""
    p = C.RAW_DIR / "ACCESS_LOG.json"
    log = json.loads(p.read_text()) if p.exists() else {}
    log[name] = {"url": url, "accessed_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
    p.write_text(json.dumps(log, indent=2))


# ---------------------------------------------------------------- daily weather
def archive_end_date() -> str:
    # ERA5 in Open-Meteo lags ~5 days; ask up to 7 days ago to avoid partial NaNs.
    return (dt.date.today() - dt.timedelta(days=7)).isoformat()


def fetch_daily(force: bool = False) -> pd.DataFrame:
    """Daily ERA5 reanalysis for every county point, 1991 -> ~7 days ago.

    We request `models=era5` explicitly: ERA5 is one consistent model for the whole
    period, which matters for trend analysis (the default 'best_match' mixes models).
    Requests are split into ~5-year chunks and cached per county to survive rate limits.
    """
    out_dir = C.RAW_DIR / "daily"
    out_dir.mkdir(parents=True, exist_ok=True)
    end = archive_end_date()
    frames = []
    for c in C.COUNTIES:
        f = out_dir / f"{c.name.replace(' ', '_')}.parquet"
        cached = pd.read_parquet(f) if f.exists() and not force else None
        start = C.START_DATE
        if cached is not None:
            last = pd.Timestamp(cached["date"].max())
            if (pd.Timestamp(end) - last).days <= 3:
                frames.append(cached)
                continue
            start = (last + pd.Timedelta(days=1)).date().isoformat()
        print(f"Open-Meteo ERA5 {c.name}: {start} -> {end}")
        parts = [] if cached is None else [cached]
        for s, e in _chunks(start, end, years=5):
            r = _get(ARCHIVE_URL, {
                "latitude": c.lat, "longitude": c.lon, "start_date": s, "end_date": e,
                "daily": ",".join(DAILY_VARS), "timezone": C.TIMEZONE, "models": "era5",
            })
            j = r.json()
            d = pd.DataFrame(j["daily"]).rename(columns={"time": "date"})
            d["date"] = pd.to_datetime(d["date"])
            d.insert(0, "county", c.name)
            d["grid_lat"], d["grid_lon"] = j.get("latitude"), j.get("longitude")
            parts.append(d)
            # Save after every chunk so a quota stop never loses finished work.
            df = pd.concat(parts, ignore_index=True).drop_duplicates(["county", "date"])
            df.to_parquet(f, index=False)
            time.sleep(_pace_seconds(s, e))
        frames.append(pd.read_parquet(f))
    _access_log("open_meteo_era5", ARCHIVE_URL)
    daily = pd.concat(frames, ignore_index=True)
    daily = daily.rename(columns={
        "precipitation_sum": "precip", "temperature_2m_max": "tmax",
        "temperature_2m_min": "tmin", "temperature_2m_mean": "tmean",
        "apparent_temperature_max": "atmax",
    })
    daily = daily.dropna(subset=["precip"])
    daily.to_parquet(C.RAW_DIR / "daily_all.parquet", index=False)
    return daily


def _pace_seconds(start: str, end: str) -> float:
    """Pause that keeps us under Open-Meteo's 600 weighted calls/minute.

    A request costs ~ (days / 14) * (variables / 10) calls, so one 5-year, 5-variable
    chunk is ~65 calls; we target ~400 calls/minute to leave headroom.
    """
    days = (pd.Timestamp(end) - pd.Timestamp(start)).days + 1
    weight = max(1.0, days / 14) * max(1.0, len(DAILY_VARS) / 10)
    return max(1.5, weight / 400 * 60)


def _chunks(start: str, end: str, years: int):
    s = pd.Timestamp(start)
    e = pd.Timestamp(end)
    while s <= e:
        ce = min(s + pd.DateOffset(years=years) - pd.Timedelta(days=1), e)
        yield s.date().isoformat(), ce.date().isoformat()
        s = ce + pd.Timedelta(days=1)


def fetch_forecast() -> pd.DataFrame:
    """Live 7-day forecast (rain, wind, Tmax) for every county point."""
    rows = []
    for c in C.COUNTIES:
        r = _get(FORECAST_URL, {
            "latitude": c.lat, "longitude": c.lon, "forecast_days": 7, "timezone": C.TIMEZONE,
            "daily": "precipitation_sum,wind_speed_10m_max,wind_gusts_10m_max,temperature_2m_max,apparent_temperature_max",
        }, tries=3, timeout=30)
        d = pd.DataFrame(r.json()["daily"]).rename(
            columns={"time": "date", "precipitation_sum": "precip_sum"})
        d.insert(0, "county", c.name)
        rows.append(d)
    fc = pd.concat(rows, ignore_index=True)
    fc["date"] = pd.to_datetime(fc["date"])
    fc["fetched_utc"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes")
    fc.to_parquet(C.RAW_DIR / "forecast_latest.parquet", index=False)
    _access_log("open_meteo_forecast", FORECAST_URL)
    return fc


# ---------------------------------------------------------------- climate drivers
SEASON_CENTER = {"DJF": 1, "JFM": 2, "FMA": 3, "MAM": 4, "AMJ": 5, "MJJ": 6,
                 "JJA": 7, "JAS": 8, "ASO": 9, "SON": 10, "OND": 11, "NDJ": 12}


def parse_oni(text: str) -> pd.DataFrame:
    """NOAA CPC ONI table -> one row per centre month (DJF -> Jan)."""
    rows = []
    for line in text.strip().splitlines()[1:]:
        p = line.split()
        if len(p) < 4 or p[0] not in SEASON_CENTER:
            continue
        rows.append({"date": pd.Timestamp(int(p[1]), SEASON_CENTER[p[0]], 1), "oni": float(p[3])})
    return pd.DataFrame(rows).sort_values("date").reset_index(drop=True)


def parse_dmi(text: str) -> pd.DataFrame:
    """NOAA PSL DMI (HadISST) long table: header 'y0 y1', then 'year v1..v12', then footer."""
    lines = text.strip().splitlines()
    y0, y1 = (int(x) for x in lines[0].split()[:2])
    rows = []
    for line in lines[1:]:
        p = line.split()
        if len(p) != 13 or not p[0].isdigit() or not (y0 <= int(p[0]) <= y1):
            continue
        for m, v in enumerate(p[1:], start=1):
            v = float(v)
            if v > -99:
                rows.append({"date": pd.Timestamp(int(p[0]), m, 1), "dmi": v})
    return pd.DataFrame(rows).sort_values("date").reset_index(drop=True)


def fetch_indices(force: bool = False) -> pd.DataFrame:
    f = C.RAW_DIR / "climate_indices.parquet"
    if f.exists() and not force:
        return pd.read_parquet(f)
    oni = parse_oni(_get(ONI_URL, timeout=60).text)
    dmi = parse_dmi(_get(DMI_URL, timeout=60).text)
    _access_log("noaa_cpc_oni", ONI_URL)
    _access_log("noaa_psl_dmi", DMI_URL)
    idx = oni.merge(dmi, on="date", how="outer").sort_values("date")
    idx.to_parquet(f, index=False)
    return idx


# ---------------------------------------------------------------- cyclones
def fetch_ibtracs(force: bool = False) -> pd.DataFrame:
    """IBTrACS v04 South Indian (SI) + North Indian (NI) basins, main tracks only."""
    f = C.RAW_DIR / "ibtracs_si_ni.parquet"
    if f.exists() and not force:
        return pd.read_parquet(f)
    cols = ["SID", "SEASON", "BASIN", "NAME", "ISO_TIME", "NATURE", "LAT", "LON",
            "WMO_WIND", "USA_WIND", "TRACK_TYPE"]
    parts = []
    for basin in ("SI", "NI"):
        url = IBTRACS_URLS[0].format(basin=basin)
        print(f"IBTrACS {basin} ...")
        r = _get(url, timeout=600)
        d = pd.read_csv(io.BytesIO(r.content), skiprows=[1], usecols=cols,
                        keep_default_na=False, na_values=[" ", ""], low_memory=False)
        parts.append(d)
        _access_log(f"ibtracs_{basin}", url)
    ib = pd.concat(parts, ignore_index=True)
    ib = ib[ib["TRACK_TYPE"].astype(str).str.lower().str.startswith("main")]
    for col in ("SEASON", "LAT", "LON", "WMO_WIND", "USA_WIND"):
        ib[col] = pd.to_numeric(ib[col], errors="coerce")
    ib["ISO_TIME"] = pd.to_datetime(ib["ISO_TIME"], errors="coerce")
    ib = ib[ib["SEASON"] >= C.CYCLONE_FIRST_SEASON].dropna(subset=["LAT", "LON", "ISO_TIME"])
    ib.to_parquet(f, index=False)
    return ib


# ---------------------------------------------------------------- boundaries + population
def fetch_boundaries(force: bool = False) -> Path:
    f = C.RAW_DIR / "kenya_adm1.geojson"
    if f.exists() and not force:
        return f
    meta = _get(GEOBOUNDARIES_API, timeout=60).json()
    url = meta.get("simplifiedGeometryGeoJSON") or meta["gjDownloadURL"]
    f.write_bytes(_get(url, timeout=300).content)
    _access_log("geoboundaries_KEN_ADM1", url)
    (C.RAW_DIR / "kenya_adm1_meta.json").write_text(json.dumps(
        {k: meta.get(k) for k in ("boundaryName", "boundaryYearRepresented", "boundaryLicense",
                                  "boundarySource", "licenseDetail", "sourceDataUpdateDate")}, indent=2))
    return f


def fetch_population(force: bool = False) -> Path:
    f = C.RAW_DIR / "ken_ppp_2020_1km_UNadj.tif"
    if f.exists() and not force:
        return f
    r = _get(WORLDPOP_URL, timeout=600)
    f.write_bytes(r.content)
    _access_log("worldpop_2020_1km_unadj", WORLDPOP_URL)
    return f


def fetch_all(force: bool = False, skip_forecast: bool = False) -> None:
    C.ensure_dirs()
    steps = [("boundaries", fetch_boundaries), ("population", fetch_population),
             ("climate indices", fetch_indices), ("IBTrACS", fetch_ibtracs),
             ("daily weather", fetch_daily)]
    for name, fn in steps:
        print(f"== {name}")
        fn(force=force)
    if not skip_forecast:
        print("== 7-day forecast")
        try:
            fetch_forecast()
        except RuntimeError as e:  # the watch tool will report 'unavailable'
            print(f"  forecast unavailable: {e}")


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    fetch_all(force=a.force)
