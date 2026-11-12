"""Model registry, promotion gate and the training CLI (tiny search on synthetic data)."""
from sentinel import model_registry as R
from sentinel import outlook, train


def test_promotion_gate_rules():
    skilful = {"test": {"bss_90ci": [0.02, 0.2], "brier": 0.2, "ece": 0.05}}
    assert R.promotion_decision(skilful, None)[0]
    unsure = {"test": {"bss_90ci": [-0.05, 0.1], "brier": 0.21, "ece": 0.05}}
    assert not R.promotion_decision(unsure, None)[0]
    active = {"test": {"bss_90ci": [-0.1, 0.05], "brier": 0.22, "ece": 0.04}}
    assert R.promotion_decision(unsure, active)[0]                      # better Brier, similar ECE
    worse_cal = {"test": {"bss_90ci": [-0.05, 0.1], "brier": 0.21, "ece": 0.2}}
    assert not R.promotion_decision(worse_cal, active)[0]


def test_train_saves_card_and_outlook_uses_registry(synth):
    cfg = train.load_config(None)
    cfg.update({"n_trials": 2, "cv": {"n_folds": 2, "fold_years": 2}})
    card = train.train(cfg, promote=False, verbose=False)
    v = card["version"]
    assert R.load_card(v)["model"]["kind"] in ("logistic", "gbm")
    assert (R.models_dir() / "outlook" / v / "model.joblib").exists()
    for k in ("brier", "bss_vs_climatology", "bss_90ci", "roc_auc", "ece", "cat_pss"):
        assert k in card["test"]
    assert R.read_registry()["active"] is None                          # --no-promote respected

    R.promote(v, "test")
    try:
        sel = outlook.registry_selection()
        assert sel["source"] == f"registry {v}" and sel["threshold"] == card["model"]["threshold"]
        m = R.load_model(v)
        assert hasattr(m, "predict_proba")
    finally:
        R.deactivate()
    assert outlook.registry_selection() is None
