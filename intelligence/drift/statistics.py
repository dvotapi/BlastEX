"""Distribution comparison for drift alerts.

Units stay on the field name (``x50_mm``, ``mean_charge_kg``). This module
never converts millimetres to metres or any other pair of units.
"""
from __future__ import annotations

import math
from typing import Any, Iterable, Sequence

import numpy as np

from intelligence.drift.types import (
    KS_ALERT,
    KS_WATCH,
    MEAN_SHIFT_ALERT,
    MEAN_SHIFT_WATCH,
    MIN_SERIES_LENGTH,
    PSI_ALERT,
    PSI_WATCH,
    SEVERITY_ALERT,
    SEVERITY_OK,
    SEVERITY_WATCH,
    DriftMetric,
    worse_severity,
)

# Longer suffixes first so ``kg_m3`` is not parsed as ``m3``.
UNIT_SUFFIXES = (
    "kg_m3",
    "mm_s",
    "m3",
    "mm",
    "ms",
    "hz",
    "pct",
    "deg",
    "kg",
    "m",
)


def unit_from_name(name: str) -> str:
    text = str(name or "").strip()
    if "." in text:
        text = text.rsplit(".", 1)[-1]
    for suffix in UNIT_SUFFIXES:
        if text.endswith(f"_{suffix}"):
            return suffix
    return ""


def as_floats(values: Iterable[Any]) -> list[float]:
    out: list[float] = []
    for raw in values:
        if raw is None or raw is True or raw is False:
            continue
        if isinstance(raw, str):
            continue
        try:
            number = float(raw)
        except (TypeError, ValueError):
            continue
        if math.isnan(number) or math.isinf(number):
            continue
        out.append(number)
    return out


def _mean(values: Sequence[float]) -> float | None:
    if not values:
        return None
    return float(sum(values) / len(values))


def _std(values: Sequence[float]) -> float | None:
    if len(values) < 2:
        return 0.0 if values else None
    mean = _mean(values)
    if mean is None:
        return None
    var = sum((item - mean) ** 2 for item in values) / (len(values) - 1)
    return float(math.sqrt(var))


def ks_statistic(baseline: Sequence[float], current: Sequence[float]) -> float | None:
    """Two-sample Kolmogorov–Smirnov statistic. No SciPy, no ``eval``."""
    a = np.sort(np.asarray(baseline, dtype=float))
    b = np.sort(np.asarray(current, dtype=float))
    if a.size == 0 or b.size == 0:
        return None
    grid = np.sort(np.concatenate([a, b]))
    cdf_a = np.searchsorted(a, grid, side="right") / a.size
    cdf_b = np.searchsorted(b, grid, side="right") / b.size
    return float(np.max(np.abs(cdf_a - cdf_b)))


def population_stability_index(
    baseline: Sequence[float],
    current: Sequence[float],
    *,
    bins: int = 10,
) -> float | None:
    """PSI on equal-width bins of the training (baseline) range."""
    a = np.asarray(baseline, dtype=float)
    b = np.asarray(current, dtype=float)
    if a.size == 0 or b.size == 0:
        return None
    low = float(np.min(a))
    high = float(np.max(a))
    if math.isclose(low, high):
        # Degenerate baseline: one bin vs "same / other".
        same = float(np.mean(np.isclose(b, low)))
        expected = np.array([1.0, 0.0], dtype=float)
        actual = np.array([same, 1.0 - same], dtype=float)
        return _psi_from_shares(expected, actual)
    edges = np.linspace(low, high, int(bins) + 1)
    expected_counts, _ = np.histogram(a, bins=edges)
    actual_counts, _ = np.histogram(b, bins=edges)
    expected = expected_counts.astype(float) / max(a.size, 1)
    actual = actual_counts.astype(float) / max(b.size, 1)
    return _psi_from_shares(expected, actual)


def _psi_from_shares(expected: np.ndarray, actual: np.ndarray) -> float:
    eps = 1e-4
    exp = np.clip(expected, eps, None)
    act = np.clip(actual, eps, None)
    # Renormalise after clipping so empty bins do not dominate.
    exp = exp / exp.sum()
    act = act / act.sum()
    return float(np.sum((act - exp) * np.log(act / exp)))


def relative_mean_shift(baseline: Sequence[float], current: Sequence[float]) -> float | None:
    base_mean = _mean(baseline)
    cur_mean = _mean(current)
    if base_mean is None or cur_mean is None:
        return None
    scale = abs(base_mean)
    if scale < 1e-12:
        scale = abs(cur_mean) if abs(cur_mean) > 1e-12 else 1.0
    return float((cur_mean - base_mean) / scale)


def classify_severity(*, psi: float | None, ks: float | None, mean_shift: float | None) -> tuple[str, list[str]]:
    severity = SEVERITY_OK
    reasons: list[str] = []
    if psi is not None:
        if psi >= PSI_ALERT:
            severity = worse_severity(severity, SEVERITY_ALERT)
            reasons.append(f"PSI={psi:.3f} ≥ {PSI_ALERT}")
        elif psi >= PSI_WATCH:
            severity = worse_severity(severity, SEVERITY_WATCH)
            reasons.append(f"PSI={psi:.3f} ≥ {PSI_WATCH}")
    if ks is not None:
        if ks >= KS_ALERT:
            severity = worse_severity(severity, SEVERITY_ALERT)
            reasons.append(f"KS={ks:.3f} ≥ {KS_ALERT}")
        elif ks >= KS_WATCH:
            severity = worse_severity(severity, SEVERITY_WATCH)
            reasons.append(f"KS={ks:.3f} ≥ {KS_WATCH}")
    if mean_shift is not None:
        magnitude = abs(mean_shift)
        if magnitude >= MEAN_SHIFT_ALERT:
            severity = worse_severity(severity, SEVERITY_ALERT)
            reasons.append(f"|Δmean|={magnitude:.3f} ≥ {MEAN_SHIFT_ALERT}")
        elif magnitude >= MEAN_SHIFT_WATCH:
            severity = worse_severity(severity, SEVERITY_WATCH)
            reasons.append(f"|Δmean|={magnitude:.3f} ≥ {MEAN_SHIFT_WATCH}")
    return severity, reasons


def compare_series(
    name: str,
    baseline: Sequence[float],
    current: Sequence[float],
    *,
    kind: str,
    role: str,
    unit: str = "",
) -> DriftMetric | None:
    base = as_floats(baseline)
    cur = as_floats(current)
    if len(base) < MIN_SERIES_LENGTH or len(cur) < MIN_SERIES_LENGTH:
        return None
    expected_unit = unit or unit_from_name(name)
    psi = population_stability_index(base, cur)
    ks = ks_statistic(base, cur)
    shift = relative_mean_shift(base, cur)
    severity, reasons = classify_severity(psi=psi, ks=ks, mean_shift=shift)
    return DriftMetric(
        name=name,
        kind=kind,
        role=role,
        unit=expected_unit,
        baseline_count=len(base),
        current_count=len(cur),
        baseline_mean=_round(_mean(base)),
        current_mean=_round(_mean(cur)),
        baseline_std=_round(_std(base)),
        current_std=_round(_std(cur)),
        psi=_round(psi, 4),
        ks=_round(ks, 4),
        mean_shift=_round(shift, 4),
        severity=severity,
        reasons=reasons,
    )


def _round(value: float | None, places: int = 6) -> float | None:
    if value is None:
        return None
    return round(float(value), places)
