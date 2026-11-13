"""scripts/ndma_compare.py on a tiny hand-checked fixture (no network)."""
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIX = Path(__file__).parent / "fixtures"
_spec = importlib.util.spec_from_file_location("ndma_compare", ROOT / "scripts" / "ndma_compare.py")
nc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(nc)


def test_mapping_comes_from_playbook():
    assert nc.ndma_mapping() == {"Normal": "Normal", "Watch": "Alert", "Warning": "Alarm", "Emergency": "Emergency"}


def test_runs_on_tiny_fixture(tmp_path):
    out_csv, out_json = tmp_path / "ndma_agreement.csv", tmp_path / "ndma_agreement.json"
    table, overall = nc.run(FIX / "ndma_phases_tiny.csv", FIX / "ndma_drought_tiny.csv", out_csv, out_json)
    assert out_csv.exists() and out_json.exists()
    t = table.set_index("county")
    # Wajir: Recovery and 'not available' months are left out -> 4 compared, 2 exact, all within one level
    w = t.loc["Wajir"]
    assert (w.months_compared, w.exact_agreement_pct, w.within_one_level_pct) == (4, 50.0, 100.0)
    assert (w.recovery_excluded, w.not_available) == (1, 1)
    # escalations: Alert in Feb (we reached Watch only in Mar -> later), Alarm in Mar (Warning same month)
    assert (w.ndma_escalations, w.we_earlier, w.same_month, w.we_later, w.not_matched) == (2, 0, 1, 1, 0)
    # Lamu: our dry-season month is excluded; we reached Watch a month before NDMA's Alert -> earlier
    lm = t.loc["Lamu"]
    assert (lm.months_compared, lm.dry_season_excluded) == (3, 1)
    assert lm.exact_agreement_pct == pytest.approx(66.7)
    assert (lm.ndma_escalations, lm.we_earlier) == (1, 1)
    a = t.loc["ALL"]
    assert a.months_compared == 7 and a.exact_agreement_pct == pytest.approx(57.1)
    assert (a.we_earlier, a.same_month, a.we_later) == (1, 1, 1)
    assert overall["period"] == "2021-01 to 2021-05"


@pytest.mark.parametrize("text,phase", [
    ("Pastoral Alarm Worsening\nCounty Alarm Worsening\n", "Alarm"),
    ("Drought Phase:ALERT-WORSENING", "Alert"),
    ("DROUGHT EW PHASE: ALARM Early Warning", "Alarm"),
    ("COUNTY RECOVERY Improving", "Recovery"),
])
def test_parse_phase_reads_bulletin_layouts(text, phase):
    assert nc.parse_phase(text)[0] == phase


@pytest.mark.parametrize("text", ["", "KILIFI COUNTY\nDROUGHT EARLY WARNING BULLETIN", "County Normal\nCounty Alert"])
def test_parse_phase_never_guesses(text):
    assert nc.parse_phase(text)[0] == nc.NA
