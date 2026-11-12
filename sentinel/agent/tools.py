"""Agent tools. Every tool reads pipeline outputs, does all arithmetic in code and returns JSON.

The LLM never calculates: percentages, levels and units are pre-computed here so the
advisory can copy numbers verbatim and the validator can check each one.
"""
from __future__ import annotations

import datetime as dt
import json

import pandas as pd

from .. import config as C
from .. import io as sio

TOWN_TO_COUNTY = {c.town.lower(): c.name for c in C.COUNTIES}

_out = sio.out_dir
_read = sio.read
_clean = sio.clean
_row = sio.row


def resolve_district(name: str | None) -> tuple[str | None, dict | None]:
    """Exact (case-insensitive) county or HQ-town match only - never guess a near miss."""
    if not name:
        return None, {"error": "missing_district", "valid_districts": C.COUNTY_NAMES}
    key = name.strip().lower().removesuffix(" county").strip()
    for c in C.COUNTY_NAMES:
        if c.lower() == key:
            return c, None
    if key in TOWN_TO_COUNTY:
        return TOWN_TO_COUNTY[key], None
    return None, {"error": "unknown_district", "requested": name,
                  "message": f"'{name}' is not one of the counties covered by Climate Sentinel. No data exists for it.",
                  "valid_districts": C.COUNTY_NAMES}


def _missing(what: str) -> dict:
    return {"available": False, "message": f"{what} is not available. Run `python run_all.py` to build it. Say 'I don't know' for this part."}


# ---------------------------------------------------------------- tools
def list_districts() -> dict:
    return {"region": C.REGION_NAME,
            "districts": [{"county": c.name, "hq_town": c.town, "zone": c.zone, "coastal": c.coastal}
                          for c in C.COUNTIES]}


def get_climate_status(district: str) -> dict:
    county, err = resolve_district(district)
    if err:
        return err
    st = _read("status.csv")
    if st is None:
        return _missing("Current climate status")
    s = _row(st, county)
    d = _read("drought.parquet")
    recent = []
    if d is not None:
        d = d[d["county"] == county].sort_values("date").tail(6)
        recent = [{"window_end": f"{r.date:%Y-%m}", "rain_3m_mm": round(r.rain_3m_mm, 1),
                   "normal_3m_mm": round(r.normal_3m_mm, 1),
                   "pct_of_normal": None if pd.isna(r.pct_of_normal) else round(r.pct_of_normal),
                   "level": r.level} for r in d.itertuples()]
    flood_lvl = s.get("observed_heavy_level")
    return {
        "county": county, "data_source": "ERA5 reanalysis via Open-Meteo (model estimate, not rain-gauge)",
        "drought": {"indicator": "3-month rainfall as % of 1991-2020 normal",
                    "window_end": s.get("drought_window_end"), "rain_3m_mm": s.get("rain_3m_mm"),
                    "normal_3m_mm": s.get("normal_3m_mm"), "pct_of_normal": s.get("pct_of_normal"),
                    "level": s.get("drought_level"), "playbook_level": _pb_level(s.get("drought_level")),
                    "last_6_windows": recent},
        "heavy_rain_observed": {"indicator": "3-day rainfall vs county 99th percentile",
                                "observed_to": s.get("observed_to"),
                                "max_3day_mm_last_7_days": s.get("observed_max_3day_mm_last7d"),
                                "ratio_to_p99": s.get("observed_ratio_to_p99"),
                                "level": flood_lvl, "playbook_level": _pb_level(flood_lvl)},
    }


def get_forecast_watch(district: str) -> dict:
    county, err = resolve_district(district)
    if err:
        return err
    w = _read("watch.csv")
    if w is None:
        return _missing("The 7-day forecast watch")
    r = _row(w, county)
    if not r:
        return _missing(f"The 7-day forecast for {county}")
    age = None
    if r.get("fetched_utc"):
        t = pd.Timestamp(r["fetched_utc"])
        t = t.tz_localize("UTC") if t.tzinfo is None else t
        age = round((pd.Timestamp.now(tz="UTC") - t).total_seconds() / 3600)
    r["forecast_age_hours"] = age
    r["stale"] = bool(age is not None and age > 24)
    r["source"] = "Open-Meteo forecast API (numerical weather model)"
    r["playbook_level"] = _pb_level(r.get("heavy_rain_level"))
    r["note"] = "County-level model forecast. It cannot say exactly when or where rain falls at a specific farm or village."
    return r


def get_seasonal_outlook(district: str) -> dict:
    county, err = resolve_district(district)
    if err:
        return err
    lv = _read("outlook_live.csv")
    if lv is None:
        return _missing("The seasonal outlook")
    r = _row(lv, county)
    if r.get("prob_below_normal") is not None:
        r["prob_below_normal_pct"] = round(100 * r["prob_below_normal"])
        r["climatological_prob_pct"] = 33
    r["meaning"] = ("Probability that total rain over the target months falls in the driest third of "
                    "historical totals for that season. Climatology (no information) is 33%.")
    return r


def get_cyclone_exposure(district: str) -> dict:
    county, err = resolve_district(district)
    if err:
        return err
    rk = _read("cyclone_ranking.csv")
    if rk is None:
        return _missing("Cyclone exposure")
    r = _row(rk, county)
    dec = _read("cyclone_per_decade.csv")
    if dec is not None:
        d = dec[dec["county"] == county]
        r["by_decade"] = [{"decade": x.decade_label, "storms": int(x.storms),
                           "storms_per_season": round(float(x.storms_per_season), 2)} for x in d.itertuples()]
    r["definition"] = (f"Distinct tropical storms (>= {C.TROPICAL_STORM_KT:g} kt) whose IBTrACS track passed within "
                       f"{C.CYCLONE_RADIUS_KM:g} km of the county boundary.")
    r["no_path_forecasts"] = "This tool does NOT predict cyclone paths, landfall or timing."
    r["official_centres"] = C.OFFICIAL_CYCLONE_CENTRES
    return r


def get_population_exposure(district: str | None = None) -> dict:
    pop = _read("population.csv")
    if pop is None:
        return _missing("Population exposure")
    out = {"source": "WorldPop 2020 1km UN-adjusted, summed inside county boundaries (estimate)"}
    if district:
        county, err = resolve_district(district)
        if err:
            return err
        r = _row(pop, county)
        out["county"] = county
        out["population_2020"] = round(r["population_2020"])
        out["census_2019_check"] = r.get("census_2019")
    region = {}
    for col in ("drought_level", "observed_heavy_level", "forecast_heavy_level", "cyclone_exposure_class"):
        t = _read(f"people_by_{col}.csv")
        if t is not None:
            region[col] = [{"level": x.level, "counties": x.counties, "people": round(x.people)} for x in t.itertuples()]
    out["region_people_by_level"] = region
    return out


def get_playbook_actions(hazard: str, level: str) -> dict:
    pb = json.loads(C.PLAYBOOK_JSON.read_text())
    hazard = (hazard or "").strip().lower()
    hazard = {"heavy rain": "flood", "heavy_rain": "flood", "rain": "flood", "floods": "flood",
              "cyclones": "cyclone", "storm": "cyclone"}.get(hazard, hazard)
    level = (level or "").strip().capitalize()
    if hazard not in pb["levels"]:
        return {"error": "unknown_hazard", "valid_hazards": list(pb["levels"])}
    if level not in pb["levels"][hazard]:
        return {"error": "no_actions_for_level", "message": f"No playbook actions for level '{level}'. "
                "Normal conditions need no hazard actions.", "valid_levels": list(pb["levels"][hazard])}
    acts = [a for a in pb["actions"] if a["hazard"] == hazard and a["level"] == level]
    return {"hazard": hazard, "level": level, "level_definition": pb["levels"][hazard][level],
            "actions": [{"id": a["id"], "action": a["action"],
                         "citation": f"{pb['sources'][a['source']]['org']}, {pb['sources'][a['source']]['title']} ({a['loc']})"}
                        for a in acts]}


def _pb_level(level: str | None) -> str | None:
    return level if level in ("Watch", "Warning", "Emergency") else None


def get_insights(district: str) -> dict:
    """Pre-computed insight card: headline, what's next, exposure, priority and triggered actions."""
    county, err = resolve_district(district)
    if err:
        return err
    from ..insights import load_insights
    data = load_insights()
    if data is None:
        return _missing("County insights")
    card = next((c for c in data["counties"] if c["county"] == county), None)
    if card is None:
        return _missing(f"Insights for {county}")
    keep = ("county", "headline", "overall_level", "priority_score", "priority_rank", "drivers", "next", "exposure")
    return {k: card[k] for k in keep if k in card}


TOOLS = {
    "list_districts": list_districts,
    "get_climate_status": get_climate_status,
    "get_forecast_watch": get_forecast_watch,
    "get_seasonal_outlook": get_seasonal_outlook,
    "get_cyclone_exposure": get_cyclone_exposure,
    "get_population_exposure": get_population_exposure,
    "get_playbook_actions": get_playbook_actions,
    "get_insights": get_insights,
}

_D = {"type": "object", "properties": {"district": {"type": "string", "description": "Kenyan county name, e.g. 'Tana River'"}},
      "required": ["district"]}
TOOL_SCHEMAS = [
    {"type": "function", "function": {"name": "list_districts", "description": "List the counties this system covers.",
                                      "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "get_climate_status", "description": "Current drought (3-month % of normal) and observed heavy-rain status for a county, with playbook levels.", "parameters": _D}},
    {"type": "function", "function": {"name": "get_forecast_watch", "description": "Next 7 days: forecast 3-day rainfall vs the county's own thresholds, coastal wind gusts, heat days.", "parameters": _D}},
    {"type": "function", "function": {"name": "get_seasonal_outlook", "description": "Probability that the next 3 months are below normal (driest third), with backtest skill verdict and confidence.", "parameters": _D}},
    {"type": "function", "function": {"name": "get_cyclone_exposure", "description": "Historical tropical-storm exposure (IBTrACS, 300 km). Does not forecast storm paths.", "parameters": _D}},
    {"type": "function", "function": {"name": "get_population_exposure", "description": "People living in the county and region-wide people per hazard level.",
                                      "parameters": {"type": "object", "properties": {"district": {"type": "string"}}}}},
    {"type": "function", "function": {"name": "get_playbook_actions", "description": "The ONLY allowed preparedness actions, with citations, for a hazard and level.",
                                      "parameters": {"type": "object", "properties": {
                                          "hazard": {"type": "string", "enum": ["drought", "flood", "cyclone"]},
                                          "level": {"type": "string", "enum": ["Watch", "Warning", "Emergency"]}},
                                          "required": ["hazard", "level"]}}},
    {"type": "function", "function": {"name": "get_insights", "description": "Summary card for a county: overall level, main drivers, what is likely next, people exposed and its priority rank among all counties.", "parameters": _D}},
]


def call_tool(name: str, args: dict) -> dict:
    fn = TOOLS.get(name)
    if fn is None:
        return {"error": "unknown_tool", "valid_tools": list(TOOLS)}
    try:
        return fn(**(args or {}))
    except TypeError as e:
        return {"error": "bad_arguments", "message": str(e)}


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
