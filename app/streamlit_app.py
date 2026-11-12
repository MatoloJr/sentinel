"""Climate Sentinel Kenya - dashboard for county disaster managers.   streamlit run app/streamlit_app.py"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sentinel import config as C  # noqa: E402

st.set_page_config(page_title="Climate Sentinel Kenya", page_icon="🌦️", layout="wide")
OUT = C.OUT_DIR
LEVEL_COLORS = {"Normal": "#4c9a6a", "Watch": "#e8c547", "Warning": "#e07b39", "Emergency": "#c0392b",
                "None recorded": "#4c9a6a", "Low": "#e8c547", "Moderate": "#e07b39", "High": "#c0392b"}
GREY = "#b8b8b8"


def banner():
    st.warning("**Planning-support tool, not an official warning system.** " + C.OFFICIAL_WARNING_NOTE +
               " Live cyclone information: [KMD](https://meteo.go.ke) and RSMC La Réunion.", icon="⚠️")


@st.cache_data(show_spinner=False)
def load(name: str, mtime: float):
    p = OUT / name
    if p.suffix == ".parquet":
        return pd.read_parquet(p)
    if p.suffix == ".json":
        return json.loads(p.read_text())
    if p.suffix == ".geojson":
        return json.loads(p.read_text())
    return pd.read_csv(p)


def get(name: str):
    p = OUT / name
    return load(name, p.stat().st_mtime) if p.exists() else None


st.title("🌦️ Climate Sentinel Kenya")
st.caption(f"{C.REGION_NAME} · drought, heavy rain and cyclone exposure · SDG 13, 2, 11, 1")
banner()

status = get("status.csv")
if status is None:
    st.error("No outputs yet. Run `python run_all.py` first (downloads data and builds everything).")
    st.stop()
summary = get("run_summary.json") or {}
st.caption(f"Weather data to **{summary.get('daily_range', ['?', '?'])[1]}** (ERA5 model estimate, not rain gauges) · "
           f"forecast fetched **{summary.get('forecast_fetched_utc') or 'not available'}** UTC · built {summary.get('built_utc', '?')}")

tabs = st.tabs(["🗺️ Hazard map", "📈 District rainfall", "🔮 Seasonal outlook", "🌀 Cyclone exposure",
                "⏱️ 7-day watch", "🤖 Advisory agent", "ℹ️ Evidence & limits"])

# ---------------------------------------------------------------- map
with tabs[0]:
    import folium
    from streamlit_folium import st_folium

    layer = st.radio("Layer", ["Drought (3-month rain vs normal)", "Heavy rain: forecast next 7 days",
                               "Heavy rain: observed last 7 days", "Cyclone exposure (1981-present)"],
                     horizontal=True)
    col = {"Drought (3-month rain vs normal)": "drought_level",
           "Heavy rain: forecast next 7 days": "forecast_heavy_level",
           "Heavy rain: observed last 7 days": "observed_heavy_level",
           "Cyclone exposure (1981-present)": "cyclone_exposure_class"}[layer]
    gj = get("counties_status.geojson")
    m = folium.Map(location=[0.3, 38.0], zoom_start=6, tiles="OpenStreetMap")

    def style(f):
        return {"fillColor": LEVEL_COLORS.get(f["properties"].get(col), GREY), "color": "#333",
                "weight": 1, "fillOpacity": 0.65}

    folium.GeoJson(gj, style_function=style, tooltip=folium.GeoJsonTooltip(
        fields=["county", "drought_level", "pct_of_normal", "forecast_heavy_level", "observed_heavy_level",
                "cyclone_exposure_class", "population_2020", "outlook_prob_below"],
        aliases=["County", "Drought", "% of normal (3 mo)", "Forecast heavy rain", "Observed heavy rain",
                 "Cyclone exposure", "Population (2020)", "P(below-normal next 3 mo)"])).add_to(m)
    if col == "cyclone_exposure_class":
        tr = get("cyclone_tracks.parquet")
        if tr is not None and len(tr):
            for sid, g in tr.sort_values("ISO_TIME").groupby("SID"):
                folium.PolyLine(g[["LAT", "LON"]].values.tolist(), weight=1.5, color="#5b6cff", opacity=0.7,
                                tooltip=f"{g['NAME'].iloc[0]} ({int(g['SEASON'].iloc[0])})").add_to(m)
    c1, c2 = st.columns([3, 2])
    with c1:
        st_folium(m, height=560, use_container_width=True, returned_objects=[])
        st.caption("Grey = not assessed (dry season or no data). Colours: green Normal · yellow Watch · orange Warning · red Emergency.")
    with c2:
        st.subheader("People by level")
        t = get(f"people_by_{col}.csv")
        if t is None:
            st.info("Not available for this layer (e.g. no forecast fetched).")
        else:
            t = t.assign(people=t["people"].round(-3).astype(int))
            st.dataframe(t[["level", "people", "n_counties", "counties"]], hide_index=True, width="stretch")
            st.caption("Population: WorldPop 2020 (1 km) summed inside county boundaries; rounded to thousands.")
        st.subheader("Levels used")
        st.markdown("- **Drought:** 3-month rain ≥75% Normal · 50–75% Watch · 25–50% Warning · <25% Emergency "
                    "(of the 1991–2020 normal; not assessed when the normal is under 30 mm).\n"
                    "- **Heavy rain:** 3-day total ≥ county p95 Watch · ≥ p99 Warning · ≥ p99.9 Emergency.\n"
                    "- **Cyclone exposure:** tropical storms within 300 km per decade: 0 None · <1 Low · 1–3 Moderate · >3 High.")

# ---------------------------------------------------------------- district
with tabs[1]:
    county = st.selectbox("County", C.COUNTY_NAMES, index=C.COUNTY_NAMES.index("Tana River"))
    mon, clim = get("monthly.parquet"), get("climatology.csv")
    m = mon[mon["county"] == county].copy()
    m["month"] = m["date"].dt.month
    m = m.merge(clim[clim["county"] == county][["month", "precip_mean"]], on="month")
    recent = m[m["date"] >= m["date"].max() - pd.DateOffset(months=23)]
    bars = alt.Chart(recent).mark_bar(color="#4a7fb5").encode(
        x=alt.X("yearmonth(date):T", title=None), y=alt.Y("precip:Q", title="Monthly rain (mm)"),
        tooltip=[alt.Tooltip("yearmonth(date):T", title="Month"), alt.Tooltip("precip:Q", format=".0f", title="Rain mm"),
                 alt.Tooltip("precip_mean:Q", format=".0f", title="Normal mm")])
    line = alt.Chart(recent).mark_line(color="#222", strokeDash=[4, 3], point=True).encode(
        x="yearmonth(date):T", y="precip_mean:Q")
    st.subheader(f"{county}: monthly rainfall vs 1991–2020 normal (last 24 months)")
    st.altair_chart((bars + line).properties(height=300), width="stretch")
    st.caption("Bars = observed (ERA5 estimate). Dashed line = normal for that calendar month.")
    d = get("drought.parquet")
    d = d[(d["county"] == county) & (d["date"] >= d["date"].max() - pd.DateOffset(months=59))]
    st.subheader("3-month rainfall as % of normal (last 5 years)")
    rule = alt.Chart(pd.DataFrame({"y": [75, 50, 25]})).mark_rule(color="#c0392b", strokeDash=[2, 2]).encode(y="y:Q")
    pct = alt.Chart(d).mark_line(point=True).encode(
        x=alt.X("date:T", title=None), y=alt.Y("pct_of_normal:Q", title="% of normal"),
        tooltip=["date:T", alt.Tooltip("pct_of_normal:Q", format=".0f"), "level"])
    st.altair_chart((pct + rule).properties(height=260), width="stretch")
    st.caption("Gaps = dry season (normal under 30 mm), not assessed. Red lines: 75 / 50 / 25% class edges.")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Seasons**")
        st.dataframe(get("seasons.csv").query("county == @county").T.astype(str), width="stretch")
    with c2:
        st.markdown("**Trends (Mann-Kendall test, Sen's slope)**")
        tr = get("trends.csv").query("county == @county")
        st.dataframe(tr[["variable", "years", "sen_slope_per_decade", "slope_95ci_per_decade", "p_value",
                         "significant_5pct"]].round(3), hide_index=True, width="stretch")

# ---------------------------------------------------------------- outlook
with tabs[2]:
    live, met, seas = get("outlook_live.csv"), get("outlook_metrics.csv"), get("outlook_by_season.csv")
    info = get("outlook_info.json") or {}
    st.subheader("Will the next 3 months be below normal (driest third)?")
    st.markdown("Climatology says **33%** every time. We publish the model's probability **only where the backtest "
                "showed skill**; elsewhere we publish 33% and say so.")
    st.dataframe(live[["county", "target_months", "prob_below_normal", "basis", "backtest_verdict", "confidence",
                       "normal_mm", "below_normal_threshold_mm", "inputs_missing"]],
                 hide_index=True, width="stretch")
    st.subheader("Backtest on the last 8 years (never seen in training)")
    sp = info.get("split", {})
    st.caption(f"Train issues {info.get('train_issue_range')} · test issues {info.get('test_issue_range')} · "
               f"model: {info.get('selection', {}).get('chosen')} · warn when P ≥ {info.get('selection', {}).get('threshold')} · "
               f"test starts {sp.get('test_start')}")
    cols = ["county", "verdict", "bss_model_vs_clim", "bss_90ci_lo", "bss_90ci_hi", "model_f1", "persistence_f1",
            "climatology_f1", "model_precision", "model_recall", "n_test"]
    st.dataframe(met[cols].round(2), hide_index=True, width="stretch")
    st.caption("BSS = Brier skill score vs climatology (above 0 = better than always saying 33%). "
               "90% interval from a year-block bootstrap. F1 is for the below-normal class.")
    if seas is not None and len(seas):
        st.markdown("**By target season (all counties pooled)**")
        st.dataframe(seas.round(2), hide_index=True, width="stretch")

# ---------------------------------------------------------------- cyclones
with tabs[3]:
    rk, dec = get("cyclone_ranking.csv"), get("cyclone_per_decade.csv")
    st.info("**This system does not predict cyclone paths.** For any live storm follow the Kenya Meteorological "
            "Department (meteo.go.ke) and RSMC La Réunion, the WMO centre for South-West Indian Ocean cyclones.")
    st.subheader("Counties ranked by tropical storms passing within 300 km")
    st.dataframe(rk[["exposure_rank", "county", "tropical_storms_300km", "storms_per_decade", "exposure_class",
                     "any_system_300km", "any_system_600km_context", "closest_approach_km", "storms_listed",
                     "seasons_covered"]], hide_index=True, width="stretch")
    coastal = [c.name for c in C.COUNTIES if c.coastal]
    dd = dec[dec["county"].isin(coastal)]
    st.altair_chart(alt.Chart(dd).mark_bar().encode(
        x=alt.X("decade_label:N", title="Decade (cyclone seasons)"), y=alt.Y("storms:Q", title="Tropical storms within 300 km"),
        color="county:N", xOffset="county:N", tooltip=["county", "decade_label", "storms", "storms_per_season"]
    ).properties(height=280), width="stretch")
    st.caption("Cyclones rarely reach Kenya: most South-West Indian Ocean storms track south of 10°S. "
               "'Any system' includes depressions below tropical-storm strength; the 600 km column is context only.")

# ---------------------------------------------------------------- watch
with tabs[4]:
    w = get("watch.csv")
    if st.button("🔄 Refresh 7-day forecast now (needs internet)"):
        with st.spinner("Fetching Open-Meteo forecast..."):
            try:
                from sentinel import fetch, watch as W
                fc = fetch.fetch_forecast()
                thr = pd.read_csv(OUT / "heavy_thresholds.csv", index_col=0)
                heat = pd.read_csv(OUT / "heat_thresholds.csv", index_col=0)["heat_threshold_c"]
                W.forecast_watch(fc, thr, heat).to_csv(OUT / "watch.csv", index=False)
                st.success("Forecast updated. Re-run `python run_all.py --offline` to refresh the map layer.")
                w = pd.read_csv(OUT / "watch.csv")
            except Exception as e:  # show, never crash the dashboard
                st.error(f"Forecast unavailable: {e}")
    if w is None:
        st.info("No forecast yet. Click refresh, or run `python run_all.py`.")
    else:
        flagged = w[w["exceeds_p99"]]
        st.metric("Counties whose forecast 3-day rain passes their own p99", len(flagged))
        st.dataframe(w, hide_index=True, width="stretch")
        st.caption("Forecast rain comes from a different model than the ERA5 history the thresholds are built on, "
                   "so treat flags as a prompt to check KMD forecasts, not a warning.")

# ---------------------------------------------------------------- agent
with tabs[5]:
    from sentinel.agent import Agent, approve, load_env, reject
    from sentinel.agent.core import load_run, runs_dir

    load_env()
    st.subheader("Ask for a county advisory")
    st.caption("The agent only uses the tools below, cites a tool result for every number, recommends only "
               "playbook actions, and every draft needs human approval.")
    q = st.text_area("Question", "Write an advisory for Tana River county for the coming weeks and months.")
    prov = st.selectbox("Model provider (free tier)", ["gemini", "groq"])
    if st.button("Draft advisory", type="primary"):
        try:
            with st.spinner("Calling tools..."):
                st.session_state["run_id"] = Agent(provider=prov).ask(q)["run_id"]
        except Exception as e:
            st.error(f"Agent unavailable: {e}")
    rid = st.session_state.get("run_id")
    runs = sorted(runs_dir().glob("*.json"), reverse=True)
    if runs:
        ids = [p.stem for p in runs[:30]]
        rid = st.selectbox("Draft", ids, index=ids.index(rid) if rid in ids else 0)
    if rid:
        run = load_run(rid)
        v = run["validation"]
        badge = {"approved": "✅ APPROVED", "rejected": "❌ REJECTED", "blocked": "⛔ BLOCKED by validator"}.get(
            run["status"], "📝 DRAFT - awaiting approval")
        st.markdown(f"**{badge}** · {run['provider']}/{run['model']} · {run['started_utc']}")
        st.markdown(f"> {run['question']}")
        st.markdown(run["advisory"])
        st.markdown(f"**Evidence check:** {'passed' if v['passed'] else 'failed'} "
                    f"({v['numbers_checked']} numbers checked against tool results)")
        for i in v["issues"]:
            st.error(i)
        with st.expander(f"Tool-call log ({len(run['tool_calls'])} calls)"):
            for t in run["tool_calls"]:
                st.markdown(f"**{t['id']}** `{t['name']}({json.dumps(t['args'])})` · {t['at_utc']} · {t['ms']} ms")
                st.json(t["result"], expanded=False)
        if run["status"] in ("draft",):
            who = st.text_input("Your name (approver)")
            c1, c2 = st.columns(2)
            if c1.button("✅ Approve advisory", disabled=not who):
                approve(rid, who)
                st.rerun()
            if c2.button("❌ Reject", disabled=not who):
                reject(rid, who)
                st.rerun()
        elif run.get("approval"):
            st.json(run["approval"])

# ---------------------------------------------------------------- evidence
with tabs[6]:
    st.subheader("Do the indicators catch real events?")
    val = get("validation.csv")
    st.dataframe(val[["event", "hazard", "county", "window", "result", "indicator_detail", "source"]],
                 hide_index=True, width="stretch")
    c1, c2 = st.columns(2)
    c1.markdown("**3 worst droughts flagged**")
    c1.dataframe(get("worst_droughts.csv"), hide_index=True, width="stretch")
    c2.markdown("**3 worst heavy-rain periods flagged**")
    c2.dataframe(get("worst_heavy_rain.csv"), hide_index=True, width="stretch")
    pop = get("population.csv")
    st.markdown("**Population check: WorldPop 2020 vs 2019 census**")
    st.dataframe(pop.round(1), hide_index=True, width="stretch")
    for doc in ("LIMITATIONS.md", "PLAYBOOK.md"):
        p = ROOT / doc
        if p.exists():
            with st.expander(doc.replace(".md", "").title()):
                st.markdown(p.read_text())
