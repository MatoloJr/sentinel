"""Deterministic insights and actions: turns pipeline outputs into a ranked, actionable card per county.

No LLM is involved. Every number is copied from an output table and every action comes from
`sentinel/playbook.json`, so cards can be shown to managers and the public without review.
Two views are produced from the same facts:
* manager: drivers, what's next (with model skill), people exposed, triggered playbook actions, priority rank
* public:  plain-language "what this means for you" text and an SMS-length message (<= 160 chars)
"""
from __future__ import annotations

import datetime as dt
import json
import math

import pandas as pd

from . import config as C
from . import io as sio

LEVEL_POINTS = {"Watch": 1, "Warning": 3, "Emergency": 6}
HAZARD_LABEL = {"drought": "Drought", "flood": "Heavy rain / flooding", "cyclone": "Cyclone season"}
TIMEFRAME = {"Emergency": "Now (next 24-48 h)", "Warning": "This week", "Watch": "Next 2-4 weeks"}
CYCLONE_SEASON_MONTHS = {11, 12, 1, 2, 3, 4}  # SW Indian Ocean season, Nov-Apr
SMS_MAX = 160

PUBLIC_ADVICE = {
    ("drought", "Watch"): "Rain has been below normal. Save and store water and follow county advice on water points and grazing.",
    ("drought", "Warning"): "Rain is well below normal. Water and pasture may run short. Conserve water and contact your ward office about water and fodder support.",
    ("drought", "Emergency"): "Severe drought conditions. Seek help early from county and Red Cross teams for water, food and livestock support.",
    ("flood", "Watch"): "Heavy rain is possible. Keep drinking water, move valuables up and know your nearest higher ground.",
    ("flood", "Warning"): "Very heavy rain is likely. Do not walk or drive through flowing water. Be ready to move to higher ground if told to.",
    ("flood", "Emergency"): "Extreme rain or flooding. Move to higher ground now if advised and follow instructions from authorities.",
    ("cyclone", "Watch"): "It is cyclone season. Follow Kenya Met Department updates, secure roofs and know your evacuation route.",
}
SMS_ADVICE = {
    ("drought", "Watch"): "Save water.",
    ("drought", "Warning"): "Save water; ask ward office about water/fodder help.",
    ("drought", "Emergency"): "Seek water, food & livestock help early.",
    ("flood", "Watch"): "Keep water, raise valuables, know high ground.",
    ("flood", "Warning"): "Avoid flowing water; be ready to move to high ground.",
    ("flood", "Emergency"): "Move to higher ground if advised.",
    ("cyclone", "Watch"): "Follow KMD updates; secure roofs.",
}


# ---------------------------------------------------------------- helpers
def _rank(level: str | None) -> int:
    return C.LEVEL_RANK.get(level or "", -1)


def _max_level(*levels: str | None) -> str:
    valid = [lv for lv in levels if lv in C.LEVEL_RANK]
    return max(valid, key=_rank) if valid else "Normal"


def _num(v, nd: int = 1):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    return round(float(v), nd)


def _playbook() -> dict:
    return json.loads(C.PLAYBOOK_JSON.read_text())


def _actions(pb: dict, hazard: str, level: str) -> list[dict]:
    if level not in ("Watch", "Warning", "Emergency"):
        return []
    out = []
    for a in pb["actions"]:
        if a["hazard"] == hazard and a["level"] == level:
            src = pb["sources"][a["source"]]
            out.append({"id": a["id"], "hazard": hazard, "level": level, "action": a["action"],
                        "timeframe": TIMEFRAME[level], "source": f"{src['org']}, {src['title']}",
                        "source_url": src.get("url"), "section": a.get("loc")})
    return out


def cyclone_level(storms_300km: int | float | None, month: int) -> str:
    """Playbook definition: Watch = cyclone season in a county with recorded storm exposure.
    Warning/Emergency need an official KMD / RSMC warning, which this tool never issues."""
    return "Watch" if (storms_300km or 0) > 0 and month in CYCLONE_SEASON_MONTHS else "Normal"


def _sms(county: str, hazard: str | None, level: str) -> str:
    if hazard is None:
        msg = f"{county}: no climate hazard alerts now. Follow KMD for daily forecasts."
    else:
        msg = f"{county} {HAZARD_LABEL[hazard].split(' /')[0]} {level.upper()}: {SMS_ADVICE[(hazard, level)]} Follow KMD/county alerts."
    return msg if len(msg) <= SMS_MAX else msg[: SMS_MAX - 1] + "…"


# ---------------------------------------------------------------- builder
def build_insights(today: dt.date | None = None) -> dict:
    """Assemble one insight card per county from outputs/. Requires status.csv."""
    today = today or dt.date.today()
    st = sio.read("status.csv")
    if st is None:
        raise FileNotFoundError("status.csv missing: run `python run_all.py` first")
    trends = sio.read("trends.csv")
    ext_tr = sio.read("extremes_trends.csv")
    live = sio.read("outlook_live.csv")
    watch = sio.read("watch.csv")
    seasons = sio.read("seasons.csv")
    pb = _playbook()

    total_pop = float(st["population_2020"].sum()) or 1.0
    cards = []
    for s in sio.records(st):
        county = s["county"]
        drought_lvl = s.get("drought_level") or "Normal"
        flood_obs = s.get("observed_heavy_level") or "Normal"
        flood_fc = s.get("forecast_heavy_level") or "Normal"
        flood_lvl = _max_level(flood_obs, flood_fc)
        cyc_lvl = cyclone_level(s.get("cyclone_storms_300km"), today.month)
        hazards = {"drought": drought_lvl if drought_lvl in C.LEVEL_RANK else "Normal",
                   "flood": flood_lvl, "cyclone": cyc_lvl}

        # ---- drivers (what is happening)
        drivers = []
        if s.get("pct_of_normal") is not None:
            drivers.append({
                "hazard": "drought", "level": drought_lvl,
                "text": f"{s['pct_of_normal']:.0f}% of normal rain over the 3 months to {s['drought_window_end']} "
                        f"({s['rain_3m_mm']} mm vs {s['normal_3m_mm']} mm normal)",
                "value": s["pct_of_normal"], "unit": "% of normal"})
        else:
            drivers.append({"hazard": "drought", "level": drought_lvl,
                            "text": "Dry season: the 3-month normal is too small to judge drought",
                            "value": None, "unit": None})
        drivers.append({
            "hazard": "flood", "level": flood_obs,
            "text": f"Wettest 3 days in the last week: {s['observed_max_3day_mm_last7d']} mm "
                    f"({s['observed_ratio_to_p99']:.0%} of the county's 1-in-100-day level)",
            "value": s["observed_max_3day_mm_last7d"], "unit": "mm / 3 days"})
        if cyc_lvl != "Normal":
            drivers.append({"hazard": "cyclone", "level": cyc_lvl,
                            "text": f"Cyclone season (Nov-Apr); {s['cyclone_storms_300km']} tropical storm(s) passed "
                                    f"within 300 km since 1981", "value": s["cyclone_storms_300km"], "unit": "storms"})

        # ---- trend
        trend = None
        if trends is not None:
            t = trends[(trends["county"] == county) & (trends["variable"] == "Annual rainfall")]
            if len(t):
                t = sio.row(t, county)
                trend = {"variable": "Annual rainfall", "slope_mm_per_decade": _num(t["sen_slope_per_decade"]),
                         "change_pct_of_mean": _num(t["change_pct_of_mean"]), "p_value": _num(t["p_value"], 3),
                         "significant": bool(t["significant_5pct"]), "years": t["years"]}
        sig_extremes = []
        if ext_tr is not None:
            e = ext_tr[(ext_tr["county"] == county) & (ext_tr["significant_5pct"].astype(str) == "True")]
            sig_extremes = [{"variable": r["variable"], "unit": r["unit"],
                             "slope_per_decade": _num(r["sen_slope_per_decade"], 2), "p_value": _num(r["p_value"], 3)}
                            for r in sio.records(e)]

        # ---- what's next
        nxt: dict = {"forecast": None, "outlook": None}
        if watch is not None and county in set(watch["county"]):
            w = sio.row(watch, county)
            nxt["forecast"] = {"level": w.get("heavy_rain_level"), "max_3day_mm": w.get("max_3day_total_mm"),
                               "window": w.get("max_3day_window"), "total_7day_mm": w.get("forecast_7day_total_mm"),
                               "p99_3day_mm": w.get("p99_3day_mm"), "gale_gusts": w.get("gale_gust_flag"),
                               "max_gust_kmh": w.get("max_gust_kmh"), "hot_days": w.get("hot_days_forecast"),
                               "fetched_utc": w.get("fetched_utc")}
        if live is not None and county in set(live["county"]):
            o = sio.row(live, county)
            skilful = not str(o.get("backtest_verdict", "")).startswith("No skill")
            p = o.get("prob_below_normal")
            if p is None:
                msg = "No seasonal outlook: the coming months are normally dry."
            elif skilful:
                msg = (f"{round(100 * p)}% chance the {o['target_months']} rain is in the driest third "
                       f"(normal chance 33%; model skill: {o['backtest_verdict'].lower()}).")
            else:
                msg = (f"No reliable signal for {o['target_months']}: the model did not beat climatology in "
                       f"testing, so plan for normal odds (33% chance of below-normal rain).")
            nxt["outlook"] = {"target_months": o.get("target_months"), "prob_below_normal": p, "skilful": skilful,
                              "verdict": o.get("backtest_verdict"), "confidence": o.get("confidence"),
                              "model_raw_prob": o.get("model_raw_prob"), "message": msg}

        # ---- rising risk?
        rising = _rank(flood_fc) > _rank(flood_obs)
        if nxt["outlook"] and nxt["outlook"]["skilful"] and (nxt["outlook"]["prob_below_normal"] or 0) >= 0.45:
            rising = True

        # ---- exposure + priority
        pop = float(s.get("population_2020") or 0)
        severity = sum(LEVEL_POINTS.get(lv, 0) for lv in hazards.values())
        pop_weight = 1 + pop / 1_000_000
        score = round(severity * pop_weight * (1.25 if rising else 1.0), 2)

        overall = _max_level(*hazards.values())
        worst_hazard = None
        if overall != "Normal":
            # ties broken by drought > flood > cyclone (slow-onset impact is broadest)
            worst_hazard = max(hazards, key=lambda h: (_rank(hazards[h]), {"drought": 2, "flood": 1, "cyclone": 0}[h]))
        if worst_hazard:
            headline = f"{HAZARD_LABEL[worst_hazard]} {overall}"
            lead = next((d["text"] for d in drivers if d["hazard"] == worst_hazard), "")
            if worst_hazard == "flood" and _rank(flood_fc) >= _rank(flood_obs) and nxt["forecast"]:
                lead = f"Forecast {nxt['forecast']['max_3day_mm']} mm in 3 days ({nxt['forecast']['window']})"
            headline = f"{headline}: {lead}"
        else:
            headline = "No hazard alerts: conditions are within the normal range"

        actions = [a for hz, lv in hazards.items() for a in _actions(pb, hz, lv)]
        actions.sort(key=lambda a: -_rank(a["level"]))

        public_lines = [PUBLIC_ADVICE[(hz, lv)] for hz, lv in sorted(hazards.items(), key=lambda kv: -_rank(kv[1]))
                        if (hz, lv) in PUBLIC_ADVICE]
        season_info = None
        if seasons is not None and county in set(seasons["county"]):
            season_info = sio.row(seasons, county).get("rainy_seasons")

        cards.append({
            "county": county, "zone": s.get("zone"), "overall_level": overall, "headline": headline,
            "hazard_levels": hazards, "drivers": drivers, "trend": trend, "significant_extreme_trends": sig_extremes,
            "next": nxt, "rising": rising,
            "exposure": {"population_2020": round(pop), "share_of_region_pct": round(100 * pop / total_pop, 1),
                         "people_at_watch_or_above": round(pop) if overall != "Normal" else 0},
            "priority_score": score,
            "priority_explained": (f"severity {severity} (Watch=1, Warning=3, Emergency=6 per hazard) x population "
                                   f"weight {pop_weight:.2f} (1 + people/1M)" + (" x 1.25 rising risk" if rising else "")),
            "actions": actions,
            "rainy_seasons": season_info,
            "public": {"summary": " ".join(public_lines) if public_lines else
                       "No climate hazard alerts right now. Keep following the daily Kenya Met Department forecast.",
                       "sms": _sms(county, worst_hazard, overall), "level": overall},
        })

    cards.sort(key=lambda c: (-c["priority_score"], c["county"]))
    for i, c in enumerate(cards, start=1):
        c["priority_rank"] = i
    region = {
        "counties_at_watch_or_above": sum(c["overall_level"] != "Normal" for c in cards),
        "counties_at_warning_or_above": sum(_rank(c["overall_level"]) >= 2 for c in cards),
        "people_at_watch_or_above": sum(c["exposure"]["people_at_watch_or_above"] for c in cards),
        "people_at_warning_or_above": sum(c["exposure"]["population_2020"] for c in cards if _rank(c["overall_level"]) >= 2),
        "rising": [c["county"] for c in cards if c["rising"]],
        "top_priorities": [c["county"] for c in cards[:3] if c["priority_score"] > 0],
    }
    return {"generated_for": today.isoformat(), "region": region, "counties": cards,
            "note": "Deterministic: numbers copied from pipeline outputs, actions only from the cited playbook. "
                    + C.OFFICIAL_WARNING_NOTE}


def save(out_dir=None) -> dict:
    out_dir = out_dir or C.OUT_DIR
    data = build_insights()
    (out_dir / "insights.json").write_text(json.dumps(sio.jsonable(data), indent=2))
    return data


def load_insights() -> dict | None:
    return sio.read_json("insights.json")


def public_view(data: dict) -> dict:
    """Strip manager-only detail for the public mode."""
    return {"generated_for": data["generated_for"], "note": data["note"],
            "counties": [{"county": c["county"], "zone": c["zone"], "level": c["overall_level"],
                          "headline": c["headline"], "summary": c["public"]["summary"], "sms": c["public"]["sms"],
                          "rainy_seasons": c.get("rainy_seasons")} for c in data["counties"]]}


if __name__ == "__main__":
    d = save()
    for c in d["counties"]:
        print(f"{c['priority_rank']:>2}. {c['county']:<11} {c['overall_level']:<9} {c['priority_score']:>6}  {c['headline']}")
