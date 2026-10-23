"""Итог подбора раскладки в JSON: варианты со скважинами, сетью и показателями.

Бесконечные значения показателей (вариант без статистики темпа) пишутся как
None: в JSON нет `inf`, а фронт показывает такой показатель прочерком.
"""
from __future__ import annotations

import math
from typing import Any

from design.layout_search.evaluate import Evaluation
from design.layout_search.search import SearchResult


def _finite(value: float | None) -> float | None:
    if value is None or not math.isfinite(value):
        return None
    return float(value)


def evaluation_to_dict(e: Evaluation) -> dict[str, Any]:
    """Вариант: параметры сетки, фланг вруба, скважины, сеть и показатели."""
    return {
        "params": dict(e.candidate.params),
        "cut_flank": e.candidate.cut_flank,
        "holes": [h.to_dict() for h in e.holes],
        "network": e.network.to_dict(),
        "rejected": bool(e.rejected),
        "reject_codes": list(e.reject_codes),
        "lsp_out": int(e.lsp_out),
        "fast_share": _finite(e.fast_share),
        "converging_length_m": _finite(e.converging_length_m),
        "outside_share": _finite(e.outside_share),
        "robust_spread": _finite(e.robust_spread),
        "hole_count": int(e.hole_count),
        "window8_max_holes": int(e.window8_max_holes),
        "downhole_ms": _finite(e.downhole_ms),
        "warnings": list(e.warnings),
    }


def result_to_dict(r: SearchResult) -> dict[str, Any]:
    """Итог поиска: лучшие варианты и сведения о ходе."""
    return {
        "best": [evaluation_to_dict(e) for e in r.best],
        "evaluated": int(r.evaluated),
        "rejected": int(r.rejected),
        "stopped_early": bool(r.stopped_early),
        "elapsed_s": float(r.elapsed_s),
        "all_rejected": bool(r.all_rejected),
        "warnings": list(r.warnings),
    }
