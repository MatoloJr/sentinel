"""HTTP API over the synthetic pipeline outputs."""
import json
from types import SimpleNamespace as NS

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client(synth):
    from sentinel.api.main import app
    return TestClient(app)


@pytest.mark.parametrize("url", ["/api/health", "/api/meta", "/api/counties", "/api/status", "/api/insights",
                                 "/api/insights?audience=public", "/api/outlook", "/api/watch", "/api/cyclones",
                                 "/api/population", "/api/validation", "/api/model", "/api/agent/runs",
                                 "/api/agent/metrics", "/api/whiplash", "/api/ndma"])
def test_endpoints_ok(client, url):
    r = client.get(url)
    assert r.status_code == 200, r.text
    json.loads(r.text)  # strict JSON (no NaN / inf)


def test_county_detail_and_alias(client):
    r = client.get("/api/county/Lodwar")
    assert r.status_code == 200
    d = r.json()
    assert d["county"] == "Turkana" and d["monthly"] and d["drought"] and d["insight"]


def test_unknown_county_404(client):
    assert client.get("/api/county/Atlantis").status_code == 404
    assert client.get("/api/insights/Atlantis").status_code == 404


def test_geojson_has_insight_props(client):
    gj = client.get("/api/counties").json()
    props = gj["features"][0]["properties"]
    assert {"overall_level", "priority_rank", "drought_level", "compound_level"} <= set(props)


def test_whiplash_endpoint_has_validation_and_blind_spot(client):
    d = client.get("/api/whiplash").json()
    assert d["validation"] and d["sensitivity"] and "blind_spot_drought_indicator_normal_pct" in d["stats"]


def test_public_insights_are_plain(client):
    pv = client.get("/api/insights?audience=public").json()
    assert all("sms" in c and "actions" not in c for c in pv["counties"])


def test_agent_ask_without_key_is_503(client, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    r = client.post("/api/agent/ask", json={"question": "Drought in Wajir?"})
    assert r.status_code == 503 and "GEMINI_API_KEY" in r.json()["detail"]


def test_agent_ask_review_flow(client, monkeypatch):
    from sentinel.agent import core

    class Fake:
        def __init__(self):
            self.n = 0
            self.chat = NS(completions=NS(create=self.create))

        def create(self, **kw):
            self.n += 1
            if self.n == 1:
                call = NS(id="c1", function=NS(name="get_cyclone_exposure", arguments=json.dumps({"district": "Lamu"})))
                return NS(choices=[NS(message=NS(content="", tool_calls=[call]))])
            return NS(choices=[NS(message=NS(content="I cannot predict cyclone paths.", tool_calls=None))])

    orig = core.Agent.__post_init__

    def fake_init(self):
        self.client = Fake()
        orig(self)

    monkeypatch.setattr(core.Agent, "__post_init__", fake_init)
    run = client.post("/api/agent/ask", json={"question": "Cyclone landfall in Lamu?"}).json()
    assert run["status"] == "draft" and run["tool_calls"][0]["id"] == "T1"
    rid = run["run_id"]
    assert client.get(f"/api/agent/runs/{rid}").status_code == 200
    assert client.post(f"/api/agent/runs/{rid}/approve", json={"approver": ""}).status_code == 422
    ok = client.post(f"/api/agent/runs/{rid}/approve", json={"approver": "Officer A"}).json()
    assert ok["status"] == "approved"
    assert client.get("/api/agent/runs/..%2Fsecrets").status_code in (400, 404)
    m = client.get("/api/agent/metrics").json()
    assert m["n_runs"] >= 1 and 0 <= m["validator_pass_rate"] <= 1
