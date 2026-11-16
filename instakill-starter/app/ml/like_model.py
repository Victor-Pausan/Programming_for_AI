"""The Lab 05 like model: a one-hidden-layer MLP trained in plain NumPy.

``load_like_model`` is the only function here that does I/O. ``predict`` is
copied from the notebook, so it reproduces the trained network exactly.
"""
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

DEFAULT_MODEL_PATH = Path(__file__).resolve().parent.parent.parent / "models" / "like_model.npz"
EXPECTED_FEATURES = ("freshness", "affinity", "popularity", "activity", "lifetime", "age")


@dataclass(frozen=True)
class LikeModel:
    W1: NDArray[np.float64]
    b1: NDArray[np.float64]
    W2: NDArray[np.float64]
    b2: NDArray[np.float64]
    mu: NDArray[np.float64]
    sd: NDArray[np.float64]
    features: tuple[str, ...]
    # constants of the signal formulas the model was trained with (train/serve skew guard)
    half_life_days: float
    popularity_days: float
    activity_cap: float
    age_cap_days: float

    @property
    def n_parameters(self) -> int:
        return int(self.W1.size + self.b1.size + self.W2.size + self.b2.size)


def load_like_model(path: Path = DEFAULT_MODEL_PATH) -> LikeModel:
    with np.load(path) as saved:
        model = LikeModel(
            W1=saved["W1"], b1=saved["b1"], W2=saved["W2"], b2=saved["b2"],
            mu=saved["mu"], sd=saved["sd"],
            features=tuple(str(f) for f in saved["features"]),
            half_life_days=float(saved["half_life_days"]),
            popularity_days=float(saved["popularity_days"]),
            activity_cap=float(saved["activity_cap"]),
            age_cap_days=float(saved["age_cap_days"]),
        )
    if model.features != EXPECTED_FEATURES:
        raise ValueError(f"model expects features {model.features}, InstaKill computes {EXPECTED_FEATURES}")
    return model


def sigmoid(z: NDArray[np.float64]) -> NDArray[np.float64]:
    return 1.0 / (1.0 + np.exp(-np.clip(z, -60, 60)))


def predict(model: LikeModel, features: NDArray[np.float64]) -> NDArray[np.float64]:
    """Raw signals (n, 6) in EXPECTED_FEATURES order -> P(like) per row. Pure."""
    x = (np.asarray(features, dtype=np.float64) - model.mu) / model.sd
    hidden = np.tanh(x @ model.W1 + model.b1)
    return sigmoid((hidden @ model.W2 + model.b2)[:, 0])
