import json
from types import SimpleNamespace as NS

import pytest

from sentinel.agent import core, tools
from sentinel.agent.core import Agent, approve, validate


# ---------------------------------------------------------------- tools
def test_unknown_district(synth):
    r = tools.get_climate_status("Kilimani Highlands")
    assert r["error"] == "unknown_district" and "Tana River" in r["valid_districts"]


def test_town_alias_and_suffix(synth):
    assert tools.resolve_district("Lodwar")[0] == "Turkana"
    assert tools.resolve_district("tana river county")[0] == "Tana River"
    assert tools.resolve_district("Nairobbi")[0] is None  # never guess near misses


def test_cyclone_tool_refuses_paths(synth):
    r = tools.get_cyclone_exposure("Lamu")
    assert "does NOT predict" in r["no_path_forecasts"] and "RSMC" in r["official_centres"]


def test_playbook_only_listed_actions(synth):
    r = tools.get_playbook_actions("drought", "Warning")
    assert 5 <= len(r["actions"]) <= 8 and all("citation" in a for a in r["actions"])
    assert tools.get_playbook_actions("drought", "Normal")["error"] == "no_actions_for_level"


def test_playbook_has_5_to_8_actions_per_level():
    pb = json.loads(core.C.PLAYBOOK_JSON.read_text())
    for hz in ("drought", "flood", "cyclone"):
        for lvl in ("Watch", "Warning", "Emergency"):
            n = sum(1 for a in pb["actions"] if a["hazard"] == hz and a["level"] == lvl)
            assert 5 <= n <= 8, (hz, lvl, n)
            assert all(a["source"] in pb["sources"] for a in pb["actions"])


def test_forecast_tool_unavailable_message(synth, tmp_path, monkeypatch):
    monkeypatch.setattr(core.C, "OUT_DIR", tmp_path)
    r = tools.get_forecast_watch("Lamu")
    assert r["available"] is False and "I don't know" in r["message"]


# ---------------------------------------------------------------- validator
RES = [{"id": "T1", "name": "get_climate_status",
        "result": {"county": "Lamu", "drought": {"pct_of_normal": 42.0, "level": "Warning", "window_end": "2026-10"}}},
       {"id": "T2", "name": "get_playbook_actions", "result": {"actions": [{"id": "DR-A1", "action": "x"}]}}]


def test_validator_passes_cited_numbers():
    v = validate("Rain is 42% of normal [T1] (window ending 2026-10 [T1]). Do DR-A1 [T2].", RES)
    assert v["passed"], v


def test_validator_blocks_invented_number():
    v = validate("Rain is 37% of normal [T1].", RES)
    assert not v["passed"] and any("37" in i for i in v["issues"])


def test_validator_blocks_uncited_number():
    v = validate("Rain is 42% of normal.", RES)
    assert not v["passed"]


def test_validator_blocks_unknown_action_and_bad_cite():
    assert not validate("Do DR-E1 [T2].", RES)["passed"]
    assert not validate("Rain is 42% of normal [T9].", RES)["passed"]


def test_validator_blocks_risk_denial():
    v = validate("There is no risk in Lamu [T1].", RES)
    assert not v["passed"] and any("downplays" in i for i in v["issues"])


# ---------------------------------------------------------------- loop + approval (scripted fake LLM)
class FakeLLM:
    """Stands in for Gemini: first asks for a tool, then answers using the result."""

    def __init__(self, final_text):
        self.final_text, self.n = final_text, 0
        self.chat = NS(completions=NS(create=self.create))

    def create(self, **kw):
        self.n += 1
        if self.n == 1:
            call = NS(id="c1", function=NS(name="get_cyclone_exposure", arguments=json.dumps({"district": "Lamu"})))
            return NS(choices=[NS(message=NS(content="", tool_calls=[call]))])
        return NS(choices=[NS(message=NS(content=self.final_text, tool_calls=None))])


def test_agent_loop_logs_and_approval(synth):
    a = Agent(provider="gemini", client=FakeLLM(
        "I cannot predict a cyclone path. Lamu recorded 1 tropical storm within 300 km [T1]."))
    run = a.ask("Where will the cyclone land?")
    assert run["tool_calls"][0]["id"] == "T1" and run["validation"]["passed"]
    assert "Kenya Meteorological Department" in run["advisory"] and run["status"] == "draft"
    done = approve(run["run_id"], "Test Reviewer")
    assert done["status"] == "approved" and done["approval"]["approved_by"] == "Test Reviewer"


def test_blocked_draft_cannot_be_approved(synth):
    run = Agent(provider="gemini", client=FakeLLM("Lamu has had 99 storms [T1].")).ask("storms?")
    assert run["status"] == "blocked"
    with pytest.raises(ValueError):
        approve(run["run_id"], "Someone")


def test_load_env_strips_inline_comments(tmp_path, monkeypatch):
    p = tmp_path / ".env"
    p.write_text('A_KEY=abc123   # https://example.com/key\nB_KEY="x # y"\nC_KEY=\n# D_KEY=zzz\n')
    for k in ("A_KEY", "B_KEY", "C_KEY", "D_KEY"):
        monkeypatch.delenv(k, raising=False)
    core.load_env(p)
    import os
    assert os.environ["A_KEY"] == "abc123"
    assert os.environ["B_KEY"] == "x # y"
    assert "C_KEY" not in os.environ and "D_KEY" not in os.environ
