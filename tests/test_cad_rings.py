"""Кольцо контура блока: нормализация и проверки (TASK-013, PR 2)."""
from __future__ import annotations

import shapely


def test_shapely_2_is_installed():
    major = int(shapely.__version__.split(".")[0])
    assert major >= 2
    for name in ("offset_curve", "polygonize", "is_valid_reason", "unary_union"):
        assert hasattr(shapely, name), name
