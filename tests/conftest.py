import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sentinel import config as C  # noqa: E402

from .synthetic import make_raw  # noqa: E402


@pytest.fixture(scope="session")
def synth(tmp_path_factory):
    """Build the full pipeline on SYNTHETIC data in a temp dir (never touches data/ or outputs/)."""
    base = tmp_path_factory.mktemp("synthetic")
    C.DATA_DIR, C.RAW_DIR = base, base / "raw"
    C.OUT_DIR, C.LOG_DIR = base / "outputs", base / "logs"
    make_raw(C.RAW_DIR)
    import run_all
    run_all.build(offline=True, skip_forecast=True, n_boot=50)
    return base
