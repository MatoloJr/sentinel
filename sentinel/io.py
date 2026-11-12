"""Cached readers for pipeline outputs, shared by the agent tools, the insights engine and the API.

Every reader keys its cache on the file's mtime, so a fresh `python run_all.py` is picked up
without restarting anything.
"""
from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from . import config as C


def out_dir() -> Path:
    return C.OUT_DIR


@lru_cache(maxsize=64)
def _csv(path: str, mtime: float) -> pd.DataFrame:  # mtime busts the cache when outputs change
    return pd.read_csv(path)


@lru_cache(maxsize=32)
def _parquet(path: str, mtime: float) -> pd.DataFrame:
    return pd.read_parquet(path)


@lru_cache(maxsize=32)
def _json(path: str, mtime: float):
    return json.loads(Path(path).read_text())


def read(name: str) -> pd.DataFrame | None:
    """CSV or parquet from outputs/ (None when the pipeline has not produced it)."""
    p = out_dir() / name
    if not p.exists():
        return None
    loader = _parquet if p.suffix == ".parquet" else _csv
    return loader(str(p), p.stat().st_mtime).copy()


def read_json(name: str):
    p = out_dir() / name
    return _json(str(p), p.stat().st_mtime) if p.exists() else None


def clean(v):
    """numpy / pandas scalar -> plain JSON-safe Python value (NaN -> None)."""
    if v is None:
        return None
    if isinstance(v, (pd.Timestamp, np.datetime64)):
        return None if pd.isna(v) else pd.Timestamp(v).isoformat()
    if hasattr(v, "item"):
        v = v.item()
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    return v


def row(df: pd.DataFrame, county: str) -> dict:
    r = df[df["county"] == county]
    return {k: clean(v) for k, v in r.iloc[0].to_dict().items()} if len(r) else {}


def records(df: pd.DataFrame | None) -> list[dict]:
    if df is None:
        return []
    return [{k: clean(v) for k, v in r.items()} for r in df.to_dict(orient="records")]


def jsonable(obj):
    """Recursively make any nested structure JSON-safe."""
    if isinstance(obj, dict):
        return {str(k): jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [jsonable(v) for v in obj]
    if isinstance(obj, pd.DataFrame):
        return records(obj)
    return clean(obj)
