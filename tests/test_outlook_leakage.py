"""The outlook must not see test-period information when training."""
import pandas as pd

from sentinel import config as C
from sentinel import outlook


def _inputs():
    mon = pd.read_parquet(C.OUT_DIR / "monthly.parquet")
    idx = pd.read_parquet(C.RAW_DIR / "climate_indices.parquet")
    return mon, idx


def test_test_period_is_last_8_years(synth):
    mon, _ = _inputs()
    sd = outlook.split_dates(mon)
    assert sd["last_complete_year"] - sd["test_start"].year + 1 == C.TEST_YEARS


def test_statistics_ignore_test_period(synth):
    """Change every test-period rainfall value: training features and thresholds must not move."""
    mon, idx = _inputs()
    ts = outlook.split_dates(mon)["test_start"]
    a, meta = outlook.build_panel(mon, idx, ts)
    mon2 = mon.copy()
    mon2.loc[mon2["date"] >= ts, "precip"] *= 5
    b, _ = outlook.build_panel(mon2, idx, ts)
    tr_a = a[a["target_end"] < ts].reset_index(drop=True)
    tr_b = b[b["target_end"] < ts].reset_index(drop=True)
    cols = outlook.NUM_FEATURES + ["p33_mm", "y", "persist_dry"]
    pd.testing.assert_frame_equal(tr_a[cols], tr_b[cols])
    # thresholds applied to TEST rows also come from training only
    te_a = a[a["issue_date"] >= ts].reset_index(drop=True)
    te_b = b[b["issue_date"] >= ts].reset_index(drop=True)
    pd.testing.assert_series_equal(te_a["p33_mm"], te_b["p33_mm"])
    assert pd.Timestamp(meta["stats_to"]) < ts


def test_training_targets_end_before_test(synth):
    mon, idx = _inputs()
    ts = outlook.split_dates(mon)["test_start"]
    panel, _ = outlook.build_panel(mon, idx, ts)
    tr = outlook._fit_rows(panel, ts)
    assert (tr["target_end"] < ts).all()
    te = outlook._test_rows(panel, ts)
    assert (te["issue_date"] + pd.DateOffset(months=1) >= ts).all()


def test_climate_indices_lagged(synth):
    """ONI used at issue month t must be the value centred at t-2 (published by then)."""
    mon, idx = _inputs()
    panel, _ = outlook.build_panel(mon, idx, outlook.split_dates(mon)["test_start"])
    oni = idx.set_index("date")["oni"]
    r = panel[panel["issue_date"] == pd.Timestamp("2005-06-01")].iloc[0]
    assert r["oni_lag"] == oni[pd.Timestamp("2005-04-01")]


def test_verdict_rules():
    assert outlook.verdict(-0.1, -0.2, 0.5, 0.3)[0].startswith("No skill")
    assert outlook.verdict(0.1, 0.02, 0.5, 0.3)[0].startswith("Skill")
    assert outlook.verdict(0.1, -0.02, 0.5, 0.3)[0].startswith("Weak")
