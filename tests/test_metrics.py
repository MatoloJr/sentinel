"""Verification metrics on hand-checkable toy inputs."""
import numpy as np
import pandas as pd
import pytest

from sentinel import metrics as M


def test_bss_climatology_is_zero_and_perfect_is_one():
    y = np.array([1, 0, 0, 1, 0, 0])
    assert M.bss(y, np.full(6, 1 / 3)) == pytest.approx(0.0)
    assert M.bss(y, y.astype(float)) == pytest.approx(1.0)
    assert M.bss(y, 1 - y.astype(float)) < 0


def test_categorical_scores_contingency():
    y = np.array([1, 1, 1, 0, 0, 0, 0, 0])
    w = np.array([1, 1, 0, 1, 0, 0, 0, 0])
    s = M.categorical_scores(y, w)
    assert (s["hits"], s["false_alarms"], s["misses"], s["correct_negatives"]) == (2, 1, 1, 4)
    assert s["pod"] == pytest.approx(2 / 3)
    assert s["far"] == pytest.approx(1 / 3)
    assert s["pofd"] == pytest.approx(1 / 5)
    assert s["csi"] == pytest.approx(2 / 4)
    assert s["pss"] == pytest.approx(2 / 3 - 1 / 5)
    # Heidke: (a+d-E)/(n-E), E = ((a+c)(a+b)+(b+d)(c+d))/n = (3*3+5*5)/8
    e = (9 + 25) / 8
    assert s["hss"] == pytest.approx((6 - e) / (8 - e))


def test_reliability_and_ece_perfectly_calibrated():
    rng = np.random.default_rng(0)
    p = rng.uniform(0, 1, 20000)
    y = (rng.uniform(0, 1, 20000) < p).astype(int)
    assert M.ece(y, p) < 0.02
    assert M.ece(y, np.clip(p + 0.3, 0, 1)) > 0.2
    r = M.reliability(y, p)
    assert r["n"].sum() == 20000


def test_relative_value_bounds():
    y = np.array([1, 0, 0] * 50, bool)
    perfect = M.relative_value(y, y.astype(float))
    assert (perfect["value"] > 0.99).all()
    clim = M.relative_value(y, np.full(len(y), 1 / 3))
    assert (clim["value"] <= 1e-9).all()


def test_rpss_climatology_zero_perfect_one():
    y = np.array([0, 1, 2, 0, 1, 2])
    assert M.rpss(y, np.full((6, 3), 1 / 3)) == pytest.approx(0.0)
    assert M.rpss(y, np.eye(3)[y]) == pytest.approx(1.0)


def test_evaluate_probabilistic_report_keys():
    rng = np.random.default_rng(1)
    n = 400
    df = pd.DataFrame({"issue_date": pd.date_range("2000-01-01", periods=n, freq="MS"),
                       "y": rng.integers(0, 2, n)})
    df["p_model"] = np.clip(df["y"] * 0.4 + rng.uniform(0, 0.5, n), 0, 1)
    df["p_persist"] = 1 / 3
    rep = M.evaluate_probabilistic(df, threshold=0.5, n_boot=50)
    for k in ("brier", "bss_vs_climatology", "bss_90ci", "roc_auc", "pr_auc", "ece", "cat_pod", "cat_pss",
              "reliability", "relative_value", "bss_vs_persistence"):
        assert k in rep
    assert rep["bss_90ci"][0] <= rep["bss_vs_climatology"] <= rep["bss_90ci"][1] + 1e-9
