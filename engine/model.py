"""
Pure-numpy gradient-boosting inference.

The artifacts are plain JSON (flat tree arrays) exported by train.py, so the
serving path needs only numpy. This removes two real production risks:

  * unpickling a joblib/scikit-learn bundle breaks whenever the runtime's
    scikit-learn build differs from the training environment (the first
    deploy of this project failed exactly this way: ModuleNotFoundError:
    No module named '_loss');
  * a pinned scikit-learn wheel pushes the serverless bundle over the size
    limit and adds a heavy import to every cold start.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

ARTIFACT_DIR = Path(__file__).resolve().parent.parent / "artifacts"


class _Booster:
    """Gradient boosting regressor with flat-array trees."""

    __slots__ = ("learning_rate", "init", "_feature", "_threshold", "_left", "_right", "_value", "_depth")

    def __init__(self, spec: dict) -> None:
        self.learning_rate = float(spec["learning_rate"])
        self.init = float(spec["init"])
        self._feature = [np.asarray(t["f"], dtype=np.int32) for t in spec["trees"]]
        self._threshold = [np.asarray(t["t"], dtype=np.float64) for t in spec["trees"]]
        self._left = [np.asarray(t["l"], dtype=np.int32) for t in spec["trees"]]
        self._right = [np.asarray(t["r"], dtype=np.int32) for t in spec["trees"]]
        self._value = [np.asarray(t["v"], dtype=np.float64) for t in spec["trees"]]
        self._depth = int(max((len(t["f"]).bit_length() for t in spec["trees"]), default=1))

    def _tree_predict(self, i: int, X: np.ndarray) -> np.ndarray:
        feature = self._feature[i]
        threshold = self._threshold[i]
        left = self._left[i]
        right = self._right[i]
        value = self._value[i]
        node = np.zeros(X.shape[0], dtype=np.int32)
        rows = np.arange(X.shape[0])
        # scikit-learn's Tree stores inputs as float32 before comparing against
        # float64 split thresholds; replicate that cast so routing is identical.
        X32 = X.astype(np.float32, copy=False)
        # tree depth is bounded; the loop exits when every row sits on a leaf
        for _ in range(self._depth + 1):
            internal = left[node] != -1
            if not internal.any():
                break
            split = feature[node]
            go_left = X32[rows, split] <= threshold[node]
            node = np.where(internal, np.where(go_left, left[node], right[node]), node)
        return value[node]

    def predict(self, X: np.ndarray) -> np.ndarray:
        out = np.full(X.shape[0], self.init, dtype=np.float64)
        for i in range(len(self._feature)):
            out += self.learning_rate * self._tree_predict(i, X)
        return out


class ValuationModel:
    """Loaded artifact: vocabs, feature order and the fitted booster."""

    def __init__(self, artifact: dict) -> None:
        self.artifact = artifact
        self.feature_order: list[str] = artifact["feature_order"]
        self.categorical: list[str] = artifact["categorical"]
        self.numerical: list[str] = artifact["numerical"]
        self.vocabs: dict[str, list[str]] = artifact["vocabs"]
        self._index = {c: {v: i for i, v in enumerate(v)} for c, v in self.vocabs.items()}
        self.median = _Booster(artifact["models"]["median"])
        self.conformal = artifact["conformal"]
        self.metrics = artifact["metrics"]
        self.target = artifact.get("target", "log(price_inr)")
        self.trained_at = artifact.get("trained_at", "")
        self.corpus = artifact.get("corpus", {})

    # -- feature assembly ---------------------------------------------------
    def encode_row(self, rec: dict) -> np.ndarray:
        row = []
        for c in self.categorical:
            vocab = self.vocabs[c]
            idx = self._index[c].get(str(rec.get(c, "")))
            row.append(float(idx if idx is not None else len(vocab) - 1))
        for c in self.numerical:
            if c == "floor_ratio":
                floors = max(float(rec.get("total_floors", 1) or 1), 1.0)
                row.append(min(max(float(rec.get("floor", 0)) / floors, 0.0), 1.0))
            else:
                row.append(float(rec.get(c, 0) or 0))
        return np.asarray(row, dtype=np.float64)

    def encode_many(self, recs: list[dict]) -> np.ndarray:
        return np.vstack([self.encode_row(r) for r in recs]) if recs else np.zeros((0, len(self.feature_order)))

    def predict_log(self, X: np.ndarray) -> np.ndarray:
        return self.median.predict(X)

    def conformal_bounds(self, property_type: str) -> tuple[float, float]:
        """p10/p90 multipliers from split-conformal calibration."""
        pair = self.conformal["by_property_type"].get(property_type) or self.conformal["global"]
        return float(pair[0]), float(pair[1])

    def predict_price(self, X: np.ndarray, property_type: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        p_med = np.exp(self.predict_log(X))
        q_lo, q_hi = self.conformal_bounds(property_type)
        return p_med, p_med * np.exp(q_lo), p_med * np.exp(q_hi)


_CACHE: dict[str, ValuationModel] = {}


def load_model(path: Path | None = None) -> ValuationModel:
    key = str(path or ARTIFACT_DIR / "model.json")
    if key not in _CACHE:
        with open(key, "r", encoding="utf-8") as fh:
            _CACHE[key] = ValuationModel(json.load(fh))
    return _CACHE[key]


_CACHE_POOL: dict[str, dict] = {}


def load_comps(path: Path | None = None) -> list[dict]:
    key = str(path or ARTIFACT_DIR / "comps.json")
    if key not in _CACHE_POOL:
        with open(key, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
        cols = payload["columns"]
        _CACHE_POOL[key] = [dict(zip(cols, row)) for row in payload["rows"]]
    return _CACHE_POOL[key]


def load_locality_stats(path: Path | None = None) -> dict[tuple[str, str, str], dict]:
    key = str(path or ARTIFACT_DIR / "locality_stats.json")
    if key not in _CACHE_POOL:
        with open(key, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
        cols = payload["columns"]
        rows = [dict(zip(cols, row)) for row in payload["rows"]]
        _CACHE_POOL[key] = {(r["city"], r["locality"], r["property_type"]): r for r in rows}
    return _CACHE_POOL[key]
