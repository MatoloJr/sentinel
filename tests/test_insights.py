"""Insight cards: deterministic levels -> playbook actions, ranking and public messages."""
import datetime as dt
import json

from sentinel import config as C
from sentinel import insights as ins


def _cards(synth):
    return ins.build_insights(today=dt.date(2026, 11, 12))["counties"]


def test_insights_written_by_pipeline(synth):
    data = json.loads((C.OUT_DIR / "insights.json").read_text())
    assert len(data["counties"]) == len(C.COUNTIES)
    assert {"region", "counties", "note"} <= set(data)


def test_actions_match_levels(synth):
    pb = json.loads(C.PLAYBOOK_JSON.read_text())
    valid = {a["id"]: (a["hazard"], a["level"]) for a in pb["actions"]}
    for c in _cards(synth):
        for a in c["actions"]:
            assert valid[a["id"]] == (a["hazard"], a["level"])           # only real playbook actions
            if a.get("compound"):                                         # brought forward by rain-after-drought
                assert a["id"] in pb["compound"]["whiplash"][c["compound_level"]]
            else:
                assert c["hazard_levels"][a["hazard"]] == a["level"]      # only for the triggered level
        if c["overall_level"] == "Normal":
            assert c["actions"] == []


def test_priority_sorted_and_ranked(synth):
    cards = _cards(synth)
    keys = [(C.LEVEL_RANK[c["overall_level"]], c["priority_score"]) for c in cards]
    assert keys == sorted(keys, reverse=True)  # alert level first, then score
    assert [c["priority_rank"] for c in cards] == list(range(1, len(cards) + 1))


def test_tana_river_forecast_flood_warning(synth):
    """Synthetic forecast puts 170 mm in 2 days over Tana River (above its p99)."""
    tana = next(c for c in _cards(synth) if c["county"] == "Tana River")
    assert C.LEVEL_RANK[tana["hazard_levels"]["flood"]] >= C.LEVEL_RANK["Warning"]
    assert any(a["hazard"] == "flood" for a in tana["actions"])
    assert tana["rising"]


def test_sms_length_and_public_text(synth):
    for c in _cards(synth):
        assert len(c["public"]["sms"]) <= ins.SMS_MAX
        assert c["county"] in c["public"]["sms"]
        assert c["public"]["summary"]


def test_cyclone_watch_only_for_active_storm_near_coast():
    assert ins.cyclone_level(650, coastal=True) == "Watch"
    assert ins.cyclone_level(1500, coastal=True) == "Normal"   # active, but far away
    assert ins.cyclone_level(None, coastal=True) == "Normal"   # no active storm / check unavailable
    assert ins.cyclone_level(300, coastal=False) == "Normal"   # inland county


def test_season_alone_does_not_put_coast_on_watch(synth):
    for c in _cards(synth):  # synthetic run has no active-storm list
        assert c["hazard_levels"]["cyclone"] == "Normal"


def test_no_skill_outlook_says_climatology(synth):
    for c in _cards(synth):
        o = c["next"]["outlook"]
        if o and o["prob_below_normal"] is not None and not o["skilful"]:
            assert "33%" in o["message"]


def test_public_view_has_no_manager_fields(synth):
    pv = ins.public_view(ins.build_insights())
    assert all("actions" not in c and "priority_score" not in c for c in pv["counties"])
