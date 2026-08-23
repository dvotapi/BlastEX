"""Deterministic discrete search space. No random sampling, no RL."""
from __future__ import annotations

import math
from itertools import product

from design.optimization.types import (
    VARIABLE_KEYS,
    VARIABLE_SPECS,
    DecisionVector,
    VariableAxis,
    VariableBound,
)


class InvalidSearchSpaceError(ValueError):
    """Raised when an axis cannot be expanded without guessing units or values."""


_SPEC_BY_KEY = {item["key"]: item for item in VARIABLE_SPECS}


def discrete_range(minimum: float, maximum: float, step: float) -> list[float]:
    """Inclusive numeric grid in the caller-declared unit. No unit conversion."""
    if step <= 0:
        raise InvalidSearchSpaceError("Шаг оси должен быть больше нуля.")
    if maximum < minimum:
        raise InvalidSearchSpaceError("Верхняя граница оси меньше нижней.")
    count = int(round((maximum - minimum) / step))
    values = [round(minimum + index * step, 10) for index in range(count + 1)]
    if not values:
        return [float(minimum)]
    if abs(values[-1] - maximum) > 1e-9:
        values.append(float(maximum))
    return values


def expand_bound(bound: VariableBound) -> VariableAxis:
    name = (bound.name or "").strip()
    if name not in VARIABLE_KEYS:
        raise InvalidSearchSpaceError(f"Неизвестная переменная оптимизации «{name}».")
    spec = _SPEC_BY_KEY[name]
    if bound.values:
        values = _normalize_values(name, spec["kind"], bound.values)
    elif spec["kind"] == "categorical":
        raise InvalidSearchSpaceError(f"Для «{spec['label']}» нужен явный список значений.")
    elif bound.minimum is None or bound.maximum is None or bound.step is None:
        raise InvalidSearchSpaceError(
            f"Для «{spec['label']}» задайте values или minimum/maximum/step в единицах {spec['unit'] or 'без конвертации'}."
        )
    else:
        values = discrete_range(float(bound.minimum), float(bound.maximum), float(bound.step))
    if not values:
        raise InvalidSearchSpaceError(f"Ось «{spec['label']}» пуста.")
    return VariableAxis(name=name, values=values, unit=spec["unit"], kind=spec["kind"])


def _normalize_values(name: str, kind: str, raw: list) -> list:
    seen: set[str] = set()
    values: list = []
    for item in raw:
        if item in (None, ""):
            continue
        if kind == "categorical":
            text = str(item).strip()
            token = text
            value: object = text
        else:
            number = float(item)
            token = f"{number:.12g}"
            value = number
        if token in seen:
            continue
        seen.add(token)
        values.append(value)
    if name in {"diameter_mm", "burden_b_m", "spacing_a_m", "delay_interval_ms"}:
        for value in values:
            if float(value) <= 0:
                raise InvalidSearchSpaceError(f"Значения оси «{name}» должны быть больше нуля.")
    if name in {"subdrill_m", "stemming_m", "inclination_deg"}:
        for value in values:
            if float(value) < 0:
                raise InvalidSearchSpaceError(f"Значения оси «{name}» не могут быть отрицательными.")
    return values


def build_space(bounds: list[VariableBound]) -> list[VariableAxis]:
    axes = [expand_bound(bound) for bound in bounds if (bound.name or "").strip()]
    names = [axis.name for axis in axes]
    if len(names) != len(set(names)):
        raise InvalidSearchSpaceError("Оси поиска не должны повторяться.")
    if not axes:
        raise InvalidSearchSpaceError("Задайте хотя бы одну переменную поиска.")
    return axes


def enumerate_vectors(
    axes: list[VariableAxis],
    max_candidates: int,
    include: DecisionVector | None = None,
) -> list[DecisionVector]:
    """Lexicographic cartesian product, thinned with a regular stride if needed."""
    if max_candidates <= 0:
        raise InvalidSearchSpaceError("Лимит кандидатов должен быть больше нуля.")
    keys = [axis.name for axis in axes]
    grids = [axis.values for axis in axes]
    combos = list(product(*grids))
    if len(combos) <= max_candidates:
        chosen = combos
    else:
        stride = int(math.ceil(len(combos) / max_candidates))
        chosen = list(combos[::stride][:max_candidates])
        if combos[-1] not in chosen:
            chosen[-1] = combos[-1]
    vectors = [DecisionVector(values=dict(zip(keys, combo))) for combo in chosen]
    if include is not None:
        fingerprint = include.fingerprint()
        if not any(item.fingerprint() == fingerprint for item in vectors):
            vectors.insert(0, include)
    return vectors
