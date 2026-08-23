"""SHAP-style local values without the ``shap`` dependency.

Default: tree-path (Saabas) attributions averaged over sklearn forest
trees. They add up to ``prediction - expected_value`` the same way SHAP
does for a single tree path. Fallback: permutation against the training
mean, which is SHAP-style for independent features.
"""
from __future__ import annotations

from typing import Any, Callable

import numpy as np

from intelligence.explainability.types import METHOD_PERMUTATION, METHOD_TREE_PATH


def sklearn_trees(estimator: Any) -> list[Any]:
    """Collect sklearn decision trees from RF / ExtraTrees / a single tree."""
    if estimator is None:
        return []
    found: list[Any] = []
    members = getattr(estimator, "estimators_", None)
    if members is not None:
        for item in members:
            tree_est = _unwrap_tree_estimator(item)
            if tree_est is not None:
                found.append(tree_est)
        return found
    tree_est = _unwrap_tree_estimator(estimator)
    return [tree_est] if tree_est is not None else []


def _unwrap_tree_estimator(item: Any) -> Any | None:
    if item is None:
        return None
    if hasattr(item, "tree_"):
        return item
    if isinstance(item, (list, tuple)) and item:
        return _unwrap_tree_estimator(item[0])
    if isinstance(item, np.ndarray) and item.size:
        return _unwrap_tree_estimator(item.reshape(-1)[0])
    return None


def _node_value(tree: Any, node: int) -> float:
    raw = np.asarray(tree.value[node], dtype=float).reshape(-1)
    return float(raw[0]) if raw.size else 0.0


def tree_path_contributions(tree_estimator: Any, vector: np.ndarray) -> tuple[np.ndarray, float, float]:
    """Saabas path values for one sklearn tree: child − parent along the path."""
    tree = tree_estimator.tree_
    n_features = int(getattr(tree_estimator, "n_features_in_", tree.n_features))
    contrib = np.zeros(n_features, dtype=float)
    node = 0
    expected = _node_value(tree, 0)
    x = np.asarray(vector, dtype=float).reshape(-1)
    feature = tree.feature
    threshold = tree.threshold
    left = tree.children_left
    right = tree.children_right
    while node >= 0 and feature[node] >= 0:
        feat = int(feature[node])
        parent_value = _node_value(tree, node)
        if feat < x.size and float(x[feat]) <= float(threshold[node]):
            node = int(left[node])
        else:
            node = int(right[node])
        if node < 0:
            break
        contrib[feat] += _node_value(tree, node) - parent_value
    prediction = expected + float(np.sum(contrib))
    return contrib, expected, prediction


def forest_path_contributions(estimator: Any, vector: np.ndarray) -> tuple[np.ndarray, float, str] | None:
    trees = sklearn_trees(estimator)
    if not trees:
        return None
    x = np.asarray(vector, dtype=float).reshape(-1)
    stacked = []
    expected_values = []
    for tree_est in trees:
        contrib, expected, _pred = tree_path_contributions(tree_est, x)
        stacked.append(contrib)
        expected_values.append(expected)
    contrib = np.mean(np.vstack(stacked), axis=0)
    expected = float(np.mean(expected_values))
    return contrib, expected, METHOD_TREE_PATH


def permutation_contributions(
    *,
    vector: np.ndarray,
    background: np.ndarray,
    predict_fn: Callable[[np.ndarray], np.ndarray],
) -> tuple[np.ndarray, float]:
    """f(x) − f(x with feature i replaced by background)."""
    x = np.asarray(vector, dtype=float).reshape(-1)
    mean = np.asarray(background, dtype=float).reshape(-1)
    if mean.size != x.size:
        mean = np.zeros_like(x)
        width = min(x.size, np.asarray(background).reshape(-1).size)
        mean[:width] = np.asarray(background, dtype=float).reshape(-1)[:width]
    base = float(np.asarray(predict_fn(x.reshape(1, -1)), dtype=float).reshape(-1)[0])
    expected = float(np.asarray(predict_fn(mean.reshape(1, -1)), dtype=float).reshape(-1)[0])
    contrib = np.zeros(x.size, dtype=float)
    for index in range(x.size):
        altered = np.array(x, copy=True)
        altered[index] = mean[index]
        other = float(np.asarray(predict_fn(altered.reshape(1, -1)), dtype=float).reshape(-1)[0])
        contrib[index] = base - other
    return contrib, expected


def background_vector(
    feature_names: list[str],
    training_matrix: list[list[float]] | np.ndarray | None,
) -> np.ndarray:
    n = len(feature_names)
    if not training_matrix:
        return np.zeros(n, dtype=float)
    X = np.asarray(training_matrix, dtype=float)
    if X.ndim != 2 or X.size == 0:
        return np.zeros(n, dtype=float)
    means = np.mean(X, axis=0)
    if means.size == n:
        return np.asarray(means, dtype=float)
    out = np.zeros(n, dtype=float)
    width = min(n, means.size)
    out[:width] = means[:width]
    return out


def local_shap_values(
    estimator: Any,
    vector: np.ndarray,
    *,
    training_matrix: list[list[float]] | np.ndarray | None = None,
    predict_fn: Callable[[np.ndarray], np.ndarray] | None = None,
    feature_names: list[str] | None = None,
) -> tuple[np.ndarray, float, str]:
    """Return (contributions, expected_value, method)."""
    x = np.asarray(vector, dtype=float).reshape(-1)
    path = forest_path_contributions(estimator, x)
    if path is not None:
        contrib, expected, method = path
        if contrib.size != x.size:
            padded = np.zeros(x.size, dtype=float)
            width = min(x.size, contrib.size)
            padded[:width] = contrib[:width]
            contrib = padded
        return contrib, float(expected), method

    names = list(feature_names or [f"f{i}" for i in range(x.size)])
    background = background_vector(names, training_matrix)
    if predict_fn is None:
        if estimator is None or not hasattr(estimator, "predict"):
            return np.zeros(x.size, dtype=float), 0.0, METHOD_PERMUTATION
        predict_fn = lambda X, est=estimator: np.asarray(est.predict(X), dtype=float)
    contrib, expected = permutation_contributions(
        vector=x,
        background=background,
        predict_fn=predict_fn,
    )
    return contrib, float(expected), METHOD_PERMUTATION
