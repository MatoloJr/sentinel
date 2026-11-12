"""Climate Sentinel HTTP API (FastAPI). Serves pipeline outputs, insights, the model card and the agent.

    uvicorn sentinel.api.main:app --reload          # dev, http://localhost:8000/api/docs
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .. import config as C
from .. import insights as ins
from .. import io as sio
from .. import metrics as M
from .. import model_registry
from ..agent import core as agent_core
from ..agent.tools import resolve_district

agent_core.load_env()

app = FastAPI(title="Climate Sentinel Kenya API", version="2.0",
              docs_url="/api/docs", redoc_url=None, openapi_url="/api/openapi.json",
              description="Drought, heavy-rain and cyclone early-warning support for 14 Kenyan counties. "
                          + C.OFFICIAL_WARNING_NOTE)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(","),
    allow_methods=["*"], allow_headers=["*"],
)


# ---------------------------------------------------------------- helpers
def _need(df, what: str):
    if df is None:
        raise HTTPException(503, f"{what} not built yet. Run `python run_all.py`.")
    return df


def _county(name: str) -> str:
    county, err = resolve_district(name)
    if err:
        raise HTTPException(404, err)
    return county


def _for_county(df, county: str) -> list[dict]:
    return [] if df is None else sio.records(df[df["county"] == county])


def _insights() -> dict:
    data = ins.load_insights()
    if data is None:
        try:  # outputs exist but insights.json predates this version
            data = ins.save()
        except FileNotFoundError:
            raise HTTPException(503, "Insights not built yet. Run `python run_all.py`.")
    return data


# ---------------------------------------------------------------- meta
@app.get("/api/health")
def health():
    s = sio.read_json("run_summary.json") or {}
    last_day = (s.get("daily_range") or [None, None])[1]
    lag = (dt.date.today() - dt.date.fromisoformat(last_day)).days if last_day else None
    return {"ok": bool(s), "built_utc": s.get("built_utc"), "daily_range": s.get("daily_range"),
            "data_lag_days": lag, "forecast_fetched_utc": s.get("forecast_fetched_utc"),
            "latest_complete_month": s.get("latest_complete_month"),
            "gemini_configured": bool(os.environ.get(agent_core.GEMINI_KEY_ENV)),
            "region": C.REGION_NAME, "official_note": C.OFFICIAL_WARNING_NOTE,
            "cyclone_centres": C.OFFICIAL_CYCLONE_CENTRES}


@app.get("/api/meta")
def meta():
    pb = json.loads(C.PLAYBOOK_JSON.read_text())
    return {"counties": [{"county": c.name, "town": c.town, "lat": c.lat, "lon": c.lon, "zone": c.zone,
                          "coastal": c.coastal} for c in C.COUNTIES],
            "levels": C.LEVELS, "playbook_levels": pb["levels"], "playbook_sources": pb["sources"],
            "thresholds": {"drought_classes": [[sio.clean(lo), sio.clean(hi), lv] for lo, hi, lv in C.DROUGHT_CLASSES],
                           "heavy_pctls": C.HEAVY_PCTLS, "gale_gust_kmh": C.GALE_GUST_KMH,
                           "cyclone_radius_km": C.CYCLONE_RADIUS_KM}}


# ---------------------------------------------------------------- map + status
@app.get("/api/counties")
def counties_geojson():
    p = sio.out_dir() / "counties_status.geojson"
    if not p.exists():
        raise HTTPException(503, "Map not built yet. Run `python run_all.py`.")
    gj = json.loads(p.read_text())
    cards = {c["county"]: c for c in _insights()["counties"]}
    for f in gj["features"]:
        props = f["properties"]
        props.update({k: sio.clean(v) if not isinstance(v, (dict, list)) else v for k, v in props.items()})
        c = cards.get(props.get("county"))
        if c:
            props["overall_level"] = c["overall_level"]
            props["priority_score"] = c["priority_score"]
            props["priority_rank"] = c["priority_rank"]
            props["cyclone_level"] = c["hazard_levels"]["cyclone"]
            props["flood_level"] = c["hazard_levels"]["flood"]
    return gj


@app.get("/api/status")
def status():
    return sio.records(_need(sio.read("status.csv"), "Status"))


@app.get("/api/insights")
def insights(audience: str = Query("manager", pattern="^(manager|public)$")):
    data = _insights()
    return ins.public_view(data) if audience == "public" else data


@app.get("/api/insights/{name}")
def county_insight(name: str):
    county = _county(name)
    card = next((c for c in _insights()["counties"] if c["county"] == county), None)
    if card is None:
        raise HTTPException(404, f"No insight card for {county}")
    return card


# ---------------------------------------------------------------- county detail
@app.get("/api/county/{name}")
def county_detail(name: str, months: int = Query(36, ge=6, le=480)):
    county = _county(name)
    mon = _need(sio.read("monthly.parquet"), "Monthly data")
    clim = sio.read("climatology.csv")
    m = mon[mon["county"] == county].sort_values("date").tail(months).copy()
    m["date"] = pd.to_datetime(m["date"])
    m["month"] = m["date"].dt.month
    if clim is not None:
        cc = clim[clim["county"] == county][["month", "precip_mean", "precip_p33", "precip_p67"]]
        m = m.merge(cc, on="month", how="left")
    m["date"] = m["date"].dt.strftime("%Y-%m")
    dro = sio.read("drought.parquet")
    drought = []
    if dro is not None:
        d = dro[dro["county"] == county].sort_values("date").copy()
        d["date"] = pd.to_datetime(d["date"]).dt.strftime("%Y-%m")
        drought = sio.records(d[["date", "rain_3m_mm", "normal_3m_mm", "pct_of_normal", "level"]])
    hr = sio.read("heavy_rain.parquet")
    daily = []
    if hr is not None:
        h = hr[hr["county"] == county].sort_values("date").tail(90).copy()
        h["date"] = pd.to_datetime(h["date"]).dt.strftime("%Y-%m-%d")
        daily = sio.records(h[["date", "precip", "rain_3d_mm", "p99_3day_mm", "level"]])
    ext = sio.read("extremes.csv")
    heat = sio.read("heat_thresholds.csv")
    thr = sio.read("heavy_thresholds.csv")
    first = lambda df: (_for_county(df, county) or [None])[0]  # noqa: E731
    return {
        "county": county, "meta": next(({"town": c.town, "lat": c.lat, "lon": c.lon, "zone": c.zone,
                                         "coastal": c.coastal} for c in C.COUNTIES if c.name == county), {}),
        "status": first(sio.read("status.csv")),
        "insight": next((c for c in _insights()["counties"] if c["county"] == county), None),
        "monthly": sio.records(m.drop(columns=["county"], errors="ignore")),
        "drought": drought, "daily_recent": daily,
        "trends": _for_county(sio.read("trends.csv"), county),
        "extremes_trends": _for_county(sio.read("extremes_trends.csv"), county),
        "extremes": _for_county(ext, county),
        "worst_events": _for_county(sio.read("per_county_worst.csv"), county),
        "season": first(sio.read("seasons.csv")),
        "heavy_thresholds": first(thr),
        "heat_threshold_c": (first(heat) or {}).get("heat_threshold_c"),
        "outlook": first(sio.read("outlook_live.csv")),
        "outlook_backtest": first(sio.read("outlook_metrics.csv")),
        "watch": first(sio.read("watch.csv")),
        "cyclone": first(sio.read("cyclone_ranking.csv")),
        "population": first(sio.read("population.csv")),
    }


# ---------------------------------------------------------------- outlook + watch
@app.get("/api/outlook")
def outlook_view():
    live = sio.records(sio.read("outlook_live.csv"))
    met = sio.records(sio.read("outlook_metrics.csv"))
    seas = sio.records(sio.read("outlook_by_season.csv"))
    info = sio.read_json("outlook_info.json") or {}
    te = sio.read("outlook_test_predictions.parquet")
    verification = None
    if te is not None and len(te):
        te = te.dropna(subset=["y", "p_model"])
        y, p = te["y"].astype(int), te["p_model"]
        thr = float((info.get("selection") or {}).get("threshold", 0.5))
        verification = {
            "n": int(len(te)), "brier": M.brier(y, p), "bss": M.bss(y, p), "roc_auc": M.roc_auc(y, p),
            "pr_auc": M.pr_auc(y, p), "ece": M.ece(y, p), "threshold": thr,
            "categorical": M.categorical_scores(y, p >= thr),
            "reliability": sio.records(M.reliability(y, p)),
            "relative_value": sio.records(M.relative_value(y, p)),
            "relative_value_persistence": sio.records(M.relative_value(y, te["p_persist"])) if "p_persist" in te else [],
        }
    return sio.jsonable({"live": live, "metrics": met, "by_season": seas, "info": info, "verification": verification})


@app.get("/api/watch")
def watch_view():
    return sio.records(sio.read("watch.csv"))


@app.get("/api/cyclones")
def cyclones():
    tr = sio.read("cyclone_tracks.parquet")
    tracks = []
    if tr is not None:
        tr = tr.sort_values(["SID", "ISO_TIME"])
        for sid, g in tr.groupby("SID"):
            wind = pd.concat([g["WMO_WIND"], g["USA_WIND"]], axis=1).max(axis=1)
            tracks.append({"sid": sid, "name": str(g["NAME"].iloc[0]), "season": int(g["SEASON"].iloc[0]),
                           "basin": str(g["BASIN"].iloc[0]), "max_wind_kt": sio.clean(wind.max()),
                           "points": [[round(float(a), 2), round(float(b), 2)] for a, b in zip(g["LON"], g["LAT"])]})
    return {"ranking": sio.records(sio.read("cyclone_ranking.csv")),
            "per_decade": sio.records(sio.read("cyclone_per_decade.csv")),
            "per_season": sio.records(sio.read("cyclone_per_season.csv")),
            "tracks": tracks, "radius_km": C.CYCLONE_RADIUS_KM, "note": C.OFFICIAL_CYCLONE_CENTRES}


@app.get("/api/population")
def population():
    out = {"by_county": sio.records(sio.read("population.csv"))}
    for col in ("drought_level", "observed_heavy_level", "forecast_heavy_level", "cyclone_exposure_class"):
        out[col] = sio.records(sio.read(f"people_by_{col}.csv"))
    return out


@app.get("/api/validation")
def validation():
    return {"events": sio.records(sio.read("validation.csv")),
            "reference_events": C.REFERENCE_EVENTS,
            "drought_class_frequency": sio.records(sio.read("drought_class_frequency.csv")),
            "worst_droughts": sio.records(sio.read("worst_droughts.csv")),
            "worst_heavy_rain": sio.records(sio.read("worst_heavy_rain.csv"))}


# ---------------------------------------------------------------- model card
@app.get("/api/model")
def model_card():
    reg = model_registry.read_registry()
    card = model_registry.active_card()
    info = sio.read_json("outlook_info.json") or {}
    return sio.jsonable({"active": card, "registry": reg, "pipeline_model_source": info.get("model_source"),
                         "pipeline_selection": info.get("selection")})


# ---------------------------------------------------------------- agent
class AskBody(BaseModel):
    question: str = Field(..., min_length=3, max_length=1000)


class ReviewBody(BaseModel):
    approver: str = Field(..., min_length=1, max_length=120)
    note: str = Field("", max_length=1000)


RUN_ID_RE = re.compile(r"^[0-9A-Za-z_-]{6,64}$")


def _run_path(run_id: str) -> Path:
    if not RUN_ID_RE.match(run_id):
        raise HTTPException(400, "bad run id")
    p = agent_core.runs_dir() / f"{run_id}.json"
    if not p.exists():
        raise HTTPException(404, "run not found")
    return p


@app.post("/api/agent/ask")
def agent_ask(body: AskBody):
    try:
        agent = agent_core.Agent()
    except RuntimeError as e:  # missing GEMINI_API_KEY
        raise HTTPException(503, str(e))
    try:
        return sio.jsonable(agent.ask(body.question))
    except Exception as e:  # upstream LLM failure
        raise HTTPException(502, f"Gemini request failed: {e}")


@app.get("/api/agent/runs")
def agent_runs(limit: int = Query(50, ge=1, le=500)):
    runs = []
    for p in sorted(agent_core.runs_dir().glob("*.json"), reverse=True)[:limit]:
        try:
            r = json.loads(p.read_text())
        except json.JSONDecodeError:
            continue
        runs.append({"run_id": r["run_id"], "question": r.get("question"), "status": r.get("status"),
                     "started_utc": r.get("started_utc"), "model": r.get("model"),
                     "validation_passed": (r.get("validation") or {}).get("passed"),
                     "n_tool_calls": len(r.get("tool_calls", []))})
    return runs


@app.get("/api/agent/runs/{run_id}")
def agent_run(run_id: str):
    return sio.jsonable(json.loads(_run_path(run_id).read_text()))


@app.post("/api/agent/runs/{run_id}/approve")
def agent_approve(run_id: str, body: ReviewBody):
    _run_path(run_id)
    try:
        return sio.jsonable(agent_core.approve(run_id, body.approver, body.note))
    except ValueError as e:
        raise HTTPException(409, str(e))


@app.post("/api/agent/runs/{run_id}/reject")
def agent_reject(run_id: str, body: ReviewBody):
    _run_path(run_id)
    return sio.jsonable(agent_core.reject(run_id, body.approver, body.note))


@app.get("/api/agent/metrics")
def agent_metrics():
    """Advisory-quality metrics over every logged run."""
    runs = []
    for p in agent_core.runs_dir().glob("*.json"):
        try:
            runs.append(json.loads(p.read_text()))
        except json.JSONDecodeError:
            pass
    n = len(runs)
    if not n:
        return {"n_runs": 0}
    passed = [r for r in runs if (r.get("validation") or {}).get("passed")]
    reviewed = [r for r in runs if r.get("status") in ("approved", "rejected")]
    approved = [r for r in reviewed if r["status"] == "approved"]
    cov_num = cov_den = 0
    for r in runs:
        for sent in re.split(r"(?<=[.!?])\s+|\n+", r.get("answer_draft") or ""):
            if agent_core.NUM_RE.search(agent_core.CITE_RE.sub(" ", sent)):
                cov_den += 1
                cov_num += bool(agent_core.CITE_RE.search(sent))
    lat = []
    for r in runs:
        try:
            lat.append((pd.Timestamp(r["finished_utc"]) - pd.Timestamp(r["started_utc"])).total_seconds())
        except (KeyError, TypeError, ValueError):
            pass
    return {"n_runs": n, "validator_pass_rate": len(passed) / n,
            "citation_coverage": cov_num / cov_den if cov_den else None,
            "reviewed": len(reviewed), "approval_rate": len(approved) / len(reviewed) if reviewed else None,
            "median_latency_s": float(pd.Series(lat).median()) if lat else None,
            "avg_tool_calls": sum(len(r.get("tool_calls", [])) for r in runs) / n}


# ---------------------------------------------------------------- optional: serve the built SPA
WEB_DIST = Path(os.environ.get("SENTINEL_WEB_DIST", C.ROOT / "web" / "dist"))
if WEB_DIST.exists():
    app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path == "api" or path.startswith("api/"):
            raise HTTPException(404, "unknown API route")
        f = WEB_DIST / path
        if path and f.is_file() and WEB_DIST.resolve() in f.resolve().parents:
            return FileResponse(f)
        return FileResponse(WEB_DIST / "index.html")
