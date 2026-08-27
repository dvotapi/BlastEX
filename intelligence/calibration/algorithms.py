"""Tree-based residual algorithms with optional boosting plugins.

Default backends are sklearn RandomForest and ExtraTrees. CatBoost, XGBoost
and LightGBM register themselves only when the library is installed.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import numpy as np

DEFAULT_ALGORITHM = "random_forest"
PLUGIN_ALGORITHMS = ("catboost", "xgboost", "lightgbm")


class ResidualAlgorithm(ABC):
    name: str
    label: str
    kind: str = "builtin"

    @abstractmethod
    def fit(self, X: np.ndarray, y: np.ndarray, *, random_state: int = 42) -> Any:
        raise NotImplementedError

    def predict(self, estimator: Any, X: np.ndarray) -> np.ndarray:
        return np.asarray(estimator.predict(X), dtype=float)


class RandomForestAlgorithm(ResidualAlgorithm):
    name = "random_forest"
    label = "Random Forest"
    kind = "builtin"

    def fit(self, X: np.ndarray, y: np.ndarray, *, random_state: int = 42) -> Any:
        from sklearn.ensemble import RandomForestRegressor

        estimator = RandomForestRegressor(
            n_estimators=40,
            max_depth=4,
            min_samples_leaf=1,
            random_state=random_state,
        )
        estimator.fit(X, y)
        return estimator


class ExtraTreesAlgorithm(ResidualAlgorithm):
    name = "extra_trees"
    label = "Extra Trees"
    kind = "builtin"

    def fit(self, X: np.ndarray, y: np.ndarray, *, random_state: int = 42) -> Any:
        from sklearn.ensemble import ExtraTreesRegressor

        estimator = ExtraTreesRegressor(
            n_estimators=40,
            max_depth=4,
            min_samples_leaf=1,
            random_state=random_state,
        )
        estimator.fit(X, y)
        return estimator


class CatBoostAlgorithm(ResidualAlgorithm):
    name = "catboost"
    label = "CatBoost"
    kind = "plugin"

    def fit(self, X: np.ndarray, y: np.ndarray, *, random_state: int = 42) -> Any:
        from catboost import CatBoostRegressor

        estimator = CatBoostRegressor(
            iterations=60,
            depth=4,
            random_seed=random_state,
            verbose=False,
            allow_writing_files=False,
        )
        estimator.fit(X, y)
        return estimator


class XGBoostAlgorithm(ResidualAlgorithm):
    name = "xgboost"
    label = "XGBoost"
    kind = "plugin"

    def fit(self, X: np.ndarray, y: np.ndarray, *, random_state: int = 42) -> Any:
        from xgboost import XGBRegressor

        estimator = XGBRegressor(
            n_estimators=60,
            max_depth=4,
            random_state=random_state,
            verbosity=0,
        )
        estimator.fit(X, y)
        return estimator


class LightGBMAlgorithm(ResidualAlgorithm):
    name = "lightgbm"
    label = "LightGBM"
    kind = "plugin"

    def fit(self, X: np.ndarray, y: np.ndarray, *, random_state: int = 42) -> Any:
        from lightgbm import LGBMRegressor

        estimator = LGBMRegressor(
            n_estimators=60,
            max_depth=4,
            random_state=random_state,
            verbosity=-1,
        )
        estimator.fit(X, y)
        return estimator


_BUILTINS: dict[str, ResidualAlgorithm] = {
    RandomForestAlgorithm.name: RandomForestAlgorithm(),
    ExtraTreesAlgorithm.name: ExtraTreesAlgorithm(),
}

_PLUGINS: dict[str, ResidualAlgorithm] = {
    CatBoostAlgorithm.name: CatBoostAlgorithm(),
    XGBoostAlgorithm.name: XGBoostAlgorithm(),
    LightGBMAlgorithm.name: LightGBMAlgorithm(),
}

_PLUGIN_IMPORTS = {
    "catboost": "catboost",
    "xgboost": "xgboost",
    "lightgbm": "lightgbm",
}


def _plugin_available(name: str) -> bool:
    module = _PLUGIN_IMPORTS.get(name)
    if not module:
        return False
    try:
        __import__(module)
    except ImportError:
        return False
    return True


def available_algorithms() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for algo in _BUILTINS.values():
        items.append({"name": algo.name, "label": algo.label, "kind": algo.kind, "available": True})
    for algo in _PLUGINS.values():
        items.append(
            {
                "name": algo.name,
                "label": algo.label,
                "kind": algo.kind,
                "available": _plugin_available(algo.name),
            }
        )
    return items


def get_algorithm(name: str | None) -> ResidualAlgorithm:
    key = str(name or DEFAULT_ALGORITHM).strip().lower().replace("-", "_")
    aliases = {"rf": "random_forest", "et": "extra_trees", "extra": "extra_trees"}
    key = aliases.get(key, key)
    if key in _BUILTINS:
        return _BUILTINS[key]
    if key in _PLUGINS:
        if not _plugin_available(key):
            available = ", ".join(item["name"] for item in available_algorithms() if item["available"])
            raise ValueError(
                f"Алгоритм «{key}» не установлен. Доступны: {available}. "
                "По умолчанию используется sklearn Random Forest."
            )
        return _PLUGINS[key]
    available = ", ".join(item["name"] for item in available_algorithms() if item["available"])
    raise ValueError(f"Неизвестный алгоритм «{name}». Доступны: {available}.")
