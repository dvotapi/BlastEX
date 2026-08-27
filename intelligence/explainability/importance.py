"""Global tree feature importance, normalised to percent shares."""
from __future__ import annotations

from typing import Any, Callable

import numpy as np

from intelligence.explainability.shap_values import sklearn_trees


def _as_predict(
    estimator: Any,
    predict_fn: Callable[[np.ndarray], np.ndarray] | None,
) -> Callable[[np.ndarray], np.ndarray]:
    if predict_fn is not None:
        return predict_fn
    return lambda X: np.asarray(estimator.predict(X), dtype=float)


def global_feature_importance(
    estimator: Any,
    feature_names: list[str],
    *,
    training_matrix: list[list[float]] | np.ndarray | None = None,
    predict_fn: Callable[[np.ndarray], np.ndarray] | None = None,
) -> np.ndarray:
    """Return a length-n vector that sums to 1 (or zeros if unknown)."""
    n = len(feature_names)
    if n == 0:
        return np.zeros(0, dtype=float)
    raw = _from_estimator_attribute(estimator, n)
    if raw is None:
        raw = _permutation_importance(
            estimator,
            feature_names,
            training_matrix,
            predict_fn=_as_predict(estimator, predict_fn),
        )
    if raw is None:
        return np.zeros(n, dtype=float)
    total = float(np.sum(np.abs(raw)))
    if total <= 1e-12:
        return np.zeros(n, dtype=float)
    return np.abs(raw) / total


def _from_estimator_attribute(estimator: Any, n: int) -> np.ndarray | None:
    values = getattr(estimator, "feature_importances_", None)
    if values is None and sklearn_trees(estimator):
        trees = sklearn_trees(estimator)
        stacked = []
        for tree_est in trees:
            item = getattr(tree_est, "feature_importances_", None)
            if item is None:
                continue
            stacked.append(np.asarray(item, dtype=float).reshape(-1))
        if stacked:
            values = np.mean(np.vstack(stacked), axis=0)
    if values is None:
        return None
    vector = np.asarray(values, dtype=float).reshape(-1)
    if vector.size != n:
        padded = np.zeros(n, dtype=float)
        width = min(n, vector.size)
        padded[:width] = vector[:width]
        return padded
    return vector


def _permutation_importance(
    estimator: Any,
    feature_names: list[str],
    training_matrix: list[list[float]] | np.ndarray | None,
    *,
    predict_fn: Callable[[np.ndarray], np.ndarray],
) -> np.ndarray | None:
    if estimator is None or not training_matrix:
        return None
    X = np.asarray(training_matrix, dtype=float)
    if X.ndim != 2 or X.shape[0] < 3 or X.shape[1] != len(feature_names):
        return None
    try:
        baseline = predict_fn(X)
    except Exception:
        return None
    y_hat = np.asarray(baseline, dtype=float).reshape(-1)
    if y_hat.size != X.shape[0]:
        return None
    center = float(np.mean(y_hat))
    denom = float(np.mean((y_hat - center) ** 2))
    if denom <= 1e-12:
        return np.zeros(X.shape[1], dtype=float)
    rng = np.random.default_rng(0)
    scores = np.zeros(X.shape[1], dtype=float)
    for index in range(X.shape[1]):
        shuffled = np.array(X, copy=True)
        rng.shuffle(shuffled[:, index])
        try:
            perturbed = np.asarray(predict_fn(shuffled), dtype=float).reshape(-1)
        except Exception:
            continue
        if perturbed.size != y_hat.size:
            continue
        mse = float(np.mean((y_hat - perturbed) ** 2))
        scores[index] = max(0.0, mse / denom)
    return scores
