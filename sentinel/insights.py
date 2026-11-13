"""Deterministic insights and actions: turns pipeline outputs into a ranked, actionable card per county.

No LLM is involved. Every number is copied from an output table, and every action comes from
`sentinel/playbook.json`, so cards can be shown to managers and the public without review.
Two views are produced from the same facts:
* manager: drivers, what's next (with model skill), people exposed, triggered playbook actions, priority rank,
  and the compound "rain after drought" (drought-to-flood whiplash) alert
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
HAZARD_LABEL = {"drought": "Drought", "flood": "Heavy rain / flooding", "cyclone": "Cyclone",
                "whiplash": "Rain after drought"}
TIMEFRAME = {"Emergency": "Now (next 24-48 h)", "Warning": "This week", "Watch": "Next 2-4 weeks"}
CYCLONE_SEASON_MONTHS = {11, 12, 1, 2, 3, 4}  # SW Indian Ocean season, Nov-Apr
SMS_MAX = 160

PUBLIC_ADVICE = {
    ("drought", "Watch"): "Rain has been below normal. Save and store water, and follow county advice on water points and grazing.",
    ("drought", "Warning"): "Rain is well below normal. Water and pasture may run short. Conserve water and contact your ward office about water and fodder support.",
    ("drought", "Emergency"): "Severe drought conditions. Seek help early from county and Red Cross teams for water, food and livestock support.",
    ("flood", "Watch"): "Heavy rain is possible. Keep drinking water, move valuables up, and know your nearest higher ground.",
    ("flood", "Warning"): "Very heavy rain is likely. Do not walk or drive through flowing water. Be ready to move to higher ground if told to.",
    ("flood", "Emergency"): "Extreme rain or flooding. Move to higher ground now if advised and follow instructions from authorities.",
    ("cyclone", "Watch"): "A tropical storm is active in the Indian Ocean. Follow Kenya Met Department updates, secure roofs and know your evacuation route.",
    ("whiplash", "Watch"): "Heavy rain is coming after a long dry spell. Dry, hard ground floods fast: keep people and animals out of dry riverbeds and treat drinking water.",
    ("whiplash", "Warning"): "Very heavy rain on drought-hit land. Flash floods can come with little warning: move animals and people away from riverbeds and low ground, and treat drinking water.",
    ("whiplash", "Emergency"): "Extreme rain on drought-hit land. Move to higher ground if advised, keep off flowing water and treat all drinking water.",
}
SMS_ADVICE = {
    ("drought", "Watch"): "Save water.",
    ("drought", "Warning"): "Save water; ask ward office about water/fodder help.",
    ("drought", "Emergency"): "Seek water, food & livestock help early.",
    ("flood", "Watch"): "Keep water, raise valuables, know high ground.",
    ("flood", "Warning"): "Avoid flowing water; be ready to move to high ground.",
    ("flood", "Emergency"): "Move to higher ground if advised.",
    ("cyclone", "Watch"): "Follow KMD updates; secure roofs.",
    ("whiplash", "Watch"): "Dry ground floods fast. Keep off riverbeds; treat water.",
    ("whiplash", "Warning"): "Flash floods likely. Move people & animals off riverbeds & low ground.",
    ("whiplash", "Emergency"): "Move to higher ground if advised; treat water.",
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


def _action_row(pb: dict, a: dict, level: str | None = None) -> dict:
    src = pb["sources"][a["source"]]
    lv = level or a["level"]
    return {"id": a["id"], "hazard": a["hazard"], "level": a["level"], "action": a["action"],
            "timeframe": TIMEFRAME[lv], "source": f"{src['org']}, {src['title']}",
            "source_url": src.get("url"), "section": a.get("loc")}


def _applies(a: dict, urban: bool) -> bool:
    """Rural/pastoral actions (water pans, fodder, de-stocking, grazing, seed) are not shown for a city."""
    return not (urban and "rural" in a.get("settings", []))


def _actions(pb: dict, hazard: str, level: str, urban: bool = False) -> list[dict]:
    if level not in ("Watch", "Warning", "Emergency"):
        return []
    return [_action_row(pb, a) for a in pb["actions"]
            if a["hazard"] == hazard and a["level"] == level and _applies(a, urban)]


def _compound_actions(pb: dict, level: str, urban: bool = False) -> list[dict]:
    """Existing cited playbook actions brought forward for rain on drought-hit land (no new actions)."""
    ids = pb.get("compound", {}).get("whiplash", {}).get(level, [])
    by_id = {a["id"]: a for a in pb["actions"]}
    out = []
    for i in ids:
        a = by_id.get(i)
        if a and _applies(a, urban):
            row = _action_row(pb, a, level)
            row["compound"] = True
            out.append(row)
    return out


def cyclone_level(active_storm_km: float | None, coastal: bool) -> str:
    """Watch only when a storm is ACTIVE within ACTIVE_STORM_WATCH_KM of a coastal county (IBTrACS
    ACTIVE list). Season alone is background information, not an alert: flagging every coastal county
    for six months a year teaches people to ignore the flag. Warning/Emergency need an official
    KMD / RSMC La Reunion warning, which this tool never issues."""
    if not coastal or active_storm_km is None or (isinstance(active_storm_km, float) and math.isnan(active_storm_km)):
        return "Normal"
    return "Watch" if active_storm_km <= C.ACTIVE_STORM_WATCH_KM else "Normal"


def _sms(county: str, hazard: str | None, level: str) -> str:
    if hazard is None:
        msg = f"{county}: no climate hazard alerts now. Follow KMD for daily forecasts."
    else:
        msg = f"{county} {HAZARD_LABEL[hazard].split(' /')[0]} {level.upper()}: {SMS_ADVICE[(hazard, level)]} Follow KMD/county alerts."
        if len(msg) > SMS_MAX:
            msg = f"{county} {HAZARD_LABEL[hazard].split(' /')[0]} {level.upper()}: {SMS_ADVICE[(hazard, level)]} Follow KMD."
    return msg if len(msg) <= SMS_MAX else msg[: SMS_MAX - 1] + "…"


def _compound_block(s: dict, county: str, nxt: dict, wsum, wep) -> dict | None:
    """Rain-after-drought card section. None when the last 12 months were not dry."""
    ap = s.get("ante_12m_pct")
    if ap is None or (isinstance(ap, float) and math.isnan(ap)) or ap > C.WHIPLASH_DRY_PCT:
        return None
    level = s.get("whiplash_level") or "Normal"
    fc = nxt.get("forecast") or {}
    deficit = s.get("ante_12m_deficit_mm")
    trigger = s.get("whiplash_trigger")
    if trigger == "forecast":
        trig_mm, trig_when = fc.get("max_3day_mm"), f"forecast for {fc.get('window')}"
    elif trigger == "observed":
        trig_mm, trig_when = s.get("observed_max_3day_mm_last7d"), "in the last 7 days"
    else:
        trig_mm, trig_when = None, None
    land = (f"the last 12 months brought {ap:.0f}% of normal rain ({s.get('ante_12m_mm')} mm vs "
            f"{s.get('ante_12m_normal_mm')} mm, to {s.get('ante_window_end')})")
    if level != "Normal":
        headline = f"{trig_mm} mm in 3 days {trig_when}, on land where {land}"
        message = ("Heavy rain is arriving on drought-hit land. Hard, bare ground sheds water, so flash floods "
                   "come faster than the rain total suggests; weakened livestock are easily lost and water sources "
                   "get contaminated. The drought indicator will show 'Normal' once it rains, but the land has not recovered.")
    else:
        headline = f"Drought-hit land: {land}"
        message = ("No heavy rain is in sight, but the land is drought-hit. If heavy rain comes, this county "
                   "moves straight to a rain-after-drought alert, so prepare flood messaging now.")
    recovery = None
    total7 = fc.get("total_7day_mm")
    if deficit and total7 is not None:
        share = 100 * float(total7) / float(deficit) if float(deficit) > 0 else None
        recovery = {"deficit_12m_mm": deficit, "forecast_7day_mm": total7,
                    "share_of_deficit_pct": None if share is None else round(min(share, 999), 0),
                    "text": (f"The next 7 days' forecast ({total7} mm) would make up {share:.0f}% of the "
                             f"12-month deficit ({deficit} mm): one wet week does not end the drought.")
                    if share is not None and share < 100 else
                    f"The next 7 days' forecast ({total7} mm) exceeds the 12-month deficit ({deficit} mm)."}
    history = None
    if wsum is not None and county in set(wsum["county"]):
        h = sio.row(wsum, county)
        history = {"p99_rain_days": h.get("p99_rain_days"),
                   "p99_rain_days_on_drought_land": h.get("p99_rain_days_on_drought_land"),
                   "share_on_drought_land_pct": h.get("share_on_drought_land_pct"),
                   "episodes_since_1991": h.get("episodes_any"),
                   "episodes_warning_plus": h.get("episodes_warning_plus"),
                   "last_episode": h.get("last_episode")}
        if wep is not None and len(wep):
            e = wep[wep["county"] == county].tail(3)
            history["recent_episodes"] = sio.records(e)
    return {"type": "drought_to_flood", "label": HAZARD_LABEL["whiplash"], "level": level,
            "headline": headline, "message": message, "trigger": trigger, "trigger_3day_mm": trig_mm,
            "antecedent_12m_pct": ap, "antecedent_12m_mm": s.get("ante_12m_mm"),
            "antecedent_12m_normal_mm": s.get("ante_12m_normal_mm"), "deficit_12m_mm": deficit,
            "antecedent_window_end": s.get("ante_window_end"), "recovery": recovery, "history": history,
            "rule": (f"Rain after drought = 3-day rain at the county's own p95 (Watch) / p99 (Warning) / p99.9 "
                     f"(Emergency), observed or forecast, when the previous 12 months had at most "
                     f"{C.WHIPLASH_DRY_PCT:.0f}% of normal rain.")}


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
    wsum = sio.read("whiplash_summary.csv")
    wep = sio.read("whiplash_episodes.csv")
    pb = _playbook()
    pop_col = "population" if "population" in st else "population_2020"  # older outputs

    total_pop = float(st[pop_col].sum()) or 1.0
    cards = []
    for s in sio.records(st):
        county = s["county"]
        drought_lvl = s.get("drought_level") or "Normal"
        flood_obs = s.get("observed_heavy_level") or "Normal"
        flood_fc = s.get("forecast_heavy_level") or "Normal"
        flood_lvl = _max_level(flood_obs, flood_fc)
        cty = C.COUNTY_BY_NAME.get(county)
        coastal = bool(cty and cty.coastal)
        urban = bool(cty and cty.urban)
        cyc_lvl = cyclone_level(s.get("active_storm_km"), coastal)
        hazards = {"drought": drought_lvl if drought_lvl in C.LEVEL_RANK else "Normal",
                   "flood": flood_lvl, "cyclone": cyc_lvl}

        # ---- drivers (what is happening)
        drivers = []
        if s.get("pct_of_normal") is not None:
            text = (f"{s['pct_of_normal']:.0f}% of normal rain over the 3 months to {s['drought_window_end']} "
                    f"({s['rain_3m_mm']} mm vs {s['normal_3m_mm']} mm normal)")
            if s.get("drought_minor_season") and s.get("drought_uncapped_level") != drought_lvl:
                text += (f". Minor season: these 3 months normally bring only {s['season_share_pct']:.0f}% of the "
                         f"year's rain, so the level is capped at Watch (raw class: {s['drought_uncapped_level']})")
            drivers.append({"hazard": "drought", "level": drought_lvl, "text": text,
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
        if coastal:
            hist = f"{s['cyclone_storms_300km']} tropical storm(s) passed within 300 km since 1981"
            checked = s.get("active_storm_check_utc")
            if cyc_lvl == "Watch":
                text = (f"Active storm {s.get('active_storm_name')} about {s.get('active_storm_km'):,.0f} km away "
                        f"(IBTrACS active list, checked {str(checked)[:16]} UTC). Follow KMD and RSMC La Reunion")
            elif not checked:
                text = (("Cyclone season (Nov-Apr). " if today.month in CYCLONE_SEASON_MONTHS else "")
                        + f"Live storm check unavailable; follow KMD and RSMC La Reunion. {hist}")
            else:
                text = (("Cyclone season (Nov-Apr): " if today.month in CYCLONE_SEASON_MONTHS else "")
                        + f"no active storm within {C.ACTIVE_STORM_WATCH_KM:,.0f} km at last check "
                          f"({str(checked)[:10]}). {hist}")
            drivers.append({"hazard": "cyclone", "level": cyc_lvl, "text": text,
                            "value": s.get("active_storm_km"), "unit": "km"})

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

        # ---- compound: rain after drought (drought-to-flood whiplash)
        compound = _compound_block(s, county, nxt, wsum, wep)
        wl = compound["level"] if compound else "Normal"
        if _rank(wl) >= 1:
            rising = True

        # ---- exposure + priority
        pop = float(s.get(pop_col) or 0)
        severity = sum(LEVEL_POINTS.get(lv, 0) for lv in hazards.values()) + LEVEL_POINTS.get(wl, 0)
        # log scale (as composite risk indices such as INFORM do for people exposed): a big city should not
        # outrank a more severe alert on head-count alone. 100k people -> 1.3, 1M -> 2.0, 4.4M -> 2.7.
        pop_weight = 1 + math.log10(1 + pop / 100_000)
        score = round(severity * pop_weight * (1.25 if rising else 1.0), 2)

        overall = _max_level(*hazards.values(), wl)
        worst_hazard = None
        if _rank(wl) >= 1 and _rank(wl) >= max(_rank(v) for v in hazards.values()):
            worst_hazard = "whiplash"  # the compound alert explains the most
        elif overall != "Normal":
            # ties broken by drought > flood > cyclone (slow-onset impact is broadest)
            worst_hazard = max(hazards, key=lambda h: (_rank(hazards[h]), {"drought": 2, "flood": 1, "cyclone": 0}[h]))
        if worst_hazard == "whiplash":
            headline = f"{HAZARD_LABEL['whiplash']} {overall}: {compound['headline']}"
        elif worst_hazard:
            headline = f"{HAZARD_LABEL[worst_hazard]} {overall}"
            lead = next((d["text"] for d in drivers if d["hazard"] == worst_hazard), "")
            if worst_hazard == "flood" and _rank(flood_fc) >= _rank(flood_obs) and nxt["forecast"]:
                lead = f"Forecast {nxt['forecast']['max_3day_mm']} mm in 3 days ({nxt['forecast']['window']})"
            headline = f"{headline}: {lead}"
        if worst_hazard is None:
            headline = "No hazard alerts: conditions are within the normal range"

        actions = [a for hz, lv in hazards.items() for a in _actions(pb, hz, lv, urban)]
        seen = {a["id"] for a in actions}
        extra = [a for a in _compound_actions(pb, wl, urban) if a["id"] not in seen]
        for a in actions:  # mark hazard actions that also serve the compound alert
            if _rank(wl) >= 1 and a["id"] in set(pb.get("compound", {}).get("whiplash", {}).get(wl, [])):
                a["compound"] = True
        actions = extra + actions  # compound actions first: they are the new, time-critical ones
        actions.sort(key=lambda a: (-_rank(a["level"]) if not a.get("compound") else -9))
        if compound:
            compound["action_ids"] = [a["id"] for a in actions if a.get("compound")]

        all_levels = {**hazards, "whiplash": wl}
        public_lines = [PUBLIC_ADVICE[(hz, lv)] for hz, lv in sorted(all_levels.items(), key=lambda kv: -_rank(kv[1]))
                        if (hz, lv) in PUBLIC_ADVICE]
        season_info = None
        if seasons is not None and county in set(seasons["county"]):
            season_info = sio.row(seasons, county).get("rainy_seasons")

        cards.append({
            "county": county, "zone": s.get("zone"), "overall_level": overall, "headline": headline,
            "hazard_levels": hazards, "compound_level": wl, "compound": compound, "drivers": drivers, "trend": trend, "significant_extreme_trends": sig_extremes,
            "next": nxt, "rising": rising,
            "exposure": {"population": round(pop), "population_source": s.get("population_source") or "WorldPop 2020",
                         "share_of_region_pct": round(100 * pop / total_pop, 1),
                         "people_at_watch_or_above": round(pop) if overall != "Normal" else 0},
            "priority_score": score,
            "priority_explained": (f"severity {severity} (Watch=1, Warning=3, Emergency=6 per hazard, compound alert "
                                   f"included) x population "
                                   f"weight {pop_weight:.2f} (1 + log10(1 + people/100k))" + (" x 1.25 rising risk" if rising else "")),
            "actions": actions,
            "rainy_seasons": season_info,
            "public": {"summary": " ".join(public_lines) if public_lines else
                       "No climate hazard alerts right now. Keep following the daily Kenya Met Department forecast.",
                       "sms": _sms(county, worst_hazard, overall), "level": overall},
        })

    # highest alert level first (a Warning never ranks below a Watch), then severity x people
    cards.sort(key=lambda c: (-_rank(c["overall_level"]), -c["priority_score"], c["county"]))
    for i, c in enumerate(cards, start=1):
        c["priority_rank"] = i
    region = {
        "counties_at_watch_or_above": sum(c["overall_level"] != "Normal" for c in cards),
        "counties_at_warning_or_above": sum(_rank(c["overall_level"]) >= 2 for c in cards),
        "people_at_watch_or_above": sum(c["exposure"]["people_at_watch_or_above"] for c in cards),
        "people_at_warning_or_above": sum(c["exposure"]["population"] for c in cards if _rank(c["overall_level"]) >= 2),
        "whiplash": [c["county"] for c in cards if _rank(c["compound_level"]) >= 1],
        "drought_hit_land": [c["county"] for c in cards if c["compound"] is not None],
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
