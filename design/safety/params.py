"""Параметры расчёта безопасных расстояний и откуда они взялись.

Коэффициенты живут в разделе справочника «Безопасные расстояния и выписка
ВМ» объекта (`blast_safety`, схема `cost/v2/schemas/safety.py`), крепость f
и группа пород по взрываемости — в справочнике пород. Проект МВ может задать
своё значение руками (`MANUAL_OVERRIDE`). Чего нет — предупреждение и
значение формы ВМ.09.03 v0.11 (как в модели себестоимости: пробел — не
исключение).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Mapping

from design.safety import SafetyIssue

__all__ = [
    "AIRBLAST_GROUP_MS",
    "FORM_DEFAULTS",
    "KN_EXTERNAL",
    "KZ_BY_FREE",
    "KZ_BY_STEMMING",
    "SafetyParams",
    "safety_params",
]

# Таблицы п. 803 ФНП 494 (сверены с текстом 11.11.2026): отношение → K.
KZ_BY_STEMMING: tuple[tuple[float, float], ...] = ((0, 1.0), (5, 0.15), (10, 0.02), (15, 0.003), (20, 0.002))
KZ_BY_FREE: tuple[tuple[float, float], ...] = ((0, 1.0), (5, 0.3), (10, 0.07), (15, 0.02), (20, 0.004))
KN_EXTERNAL: tuple[tuple[float, float], ...] = ((0, 1.0), (1, 0.5), (2, 0.3), (3, 0.1), (4, 0.03))

# Заряды с разницей моментов меньше 10 мс по УВВ — одновременные: поправки
# п. 806 заданы только для интервалов от 10 мс (решение владельца В1).
AIRBLAST_GROUP_MS = 10.0

# Значения формы ВМ.09.03 v0.11 (блок 66) — берутся, когда записи справочника
# нет. IX группа и мороз в форме «да»: без справочника расчёт идёт с запасом.
FORM_DEFAULTS: dict[str, Any] = {
    "k_ground": 5.0,
    "k_structure": 2.0,
    "alpha_blast": 1.0,
    "people_min_m": 200.0,
    "k_mech": 0.667,
    "rock_group_ix": True,
    "rock_group_v_reduce": False,
    "frost": True,
    "buildings_damaged": False,
    "relief_height_m": None,
    "slope_angle_deg": None,
    "delay_group_ms": 20.0,
    "hardness_f": 14.0,
}

_NUMBERS = ("k_ground", "k_structure", "alpha_blast", "people_min_m", "k_mech", "delay_group_ms")
_OPTIONAL_NUMBERS = ("relief_height_m", "slope_angle_deg")
_FLAGS = ("rock_group_ix", "rock_group_v_reduce", "frost", "buildings_damaged")
_TABLES = {"kz_by_stemming": KZ_BY_STEMMING, "kz_by_free": KZ_BY_FREE, "kn_external": KN_EXTERNAL}

# Группа пород по взрываемости у записи справочника пород (п. 804).
ROCK_GROUP_IX_PLUS = "IX_PLUS"
ROCK_GROUP_VI_VIII = "VI_VIII"
ROCK_GROUP_V_MINUS = "V_MINUS"


@dataclass(frozen=True)
class SafetyParams:
    """Всё, что расчёт берёт не из проекта блока. `sources` — происхождение по полю."""

    k_ground: float = 5.0
    k_structure: float = 2.0
    alpha_blast: float = 1.0
    people_min_m: float = 200.0
    k_mech: float = 0.667
    rock_group_ix: bool = True
    rock_group_v_reduce: bool = False
    frost: bool = True
    buildings_damaged: bool = False
    relief_height_m: float | None = None
    slope_angle_deg: float | None = None
    delay_group_ms: float = 20.0
    hardness_f: float = 14.0
    kz_by_stemming: tuple[tuple[float, float], ...] = KZ_BY_STEMMING
    kz_by_free: tuple[tuple[float, float], ...] = KZ_BY_FREE
    kn_external: tuple[tuple[float, float], ...] = KN_EXTERNAL
    # Ручная опасная зона проекта МВ: вид зоны → (значение, причина).
    manual_zones: Mapping[str, tuple[float, str]] = field(default_factory=dict)
    sources: Mapping[str, str] = field(default_factory=dict)
    issues: tuple[SafetyIssue, ...] = ()

    def source(self, name: str) -> str:
        return self.sources.get(name, "REFERENCE")


def safety_params(
    site_safety: Mapping[str, Any] | None = None,
    rock: Mapping[str, Any] | None = None,
    overrides: Mapping[str, Any] | None = None,
    manual_zones: Mapping[str, tuple[float, str]] | None = None,
) -> SafetyParams:
    """Собрать параметры: проект МВ → порода → справочник объекта → форма v0.11.

    `site_safety` — payload записи `blast_safety` объекта (None — записи
    нет), `rock` — payload записи породы блока (`hardness_f`,
    `blast_rock_group`), `overrides` — значения, заданные в проекте МВ руками.
    """

    issues: list[SafetyIssue] = []
    sources: dict[str, str] = {}
    values: dict[str, Any] = {}
    site = _site_payload(site_safety, issues)
    manual = _manual_values(overrides, issues)
    if site_safety is None:
        issues.append(
            SafetyIssue(
                "warning",
                "safety_reference_missing",
                "У объекта нет записи «Безопасные расстояния и выписка ВМ»: коэффициенты взяты по форме "
                "ВМ.09.03 v0.11 (K_г 5, K_с 2, α 1, IX группа и мороз — да).",
            )
        )

    for name in (*_NUMBERS, *_OPTIONAL_NUMBERS, *_FLAGS):
        if name in manual:
            values[name], sources[name] = _coerce(name, manual[name]), "MANUAL_OVERRIDE"
        elif site.get(name) is not None:
            values[name], sources[name] = _coerce(name, site[name]), "REFERENCE"
        else:
            values[name], sources[name] = FORM_DEFAULTS[name], "REFERENCE"

    for name, default in _TABLES.items():
        rows = site.get(name)
        values[name] = _table(rows) if rows else default
        sources[name] = "REFERENCE"

    # Группа пород у породы главнее флагов объекта (решение владельца В9).
    group = str((rock or {}).get("blast_rock_group") or "")
    if "rock_group_ix" not in manual and group:
        values["rock_group_ix"] = group == ROCK_GROUP_IX_PLUS
        sources["rock_group_ix"] = "REFERENCE"
        if group != ROCK_GROUP_V_MINUS and "rock_group_v_reduce" not in manual:
            values["rock_group_v_reduce"] = False
    if values["rock_group_ix"] and values["rock_group_v_reduce"]:
        issues.append(
            SafetyIssue(
                "warning",
                "rock_group_conflict",
                "Отмечены и породы IX группы, и уменьшение УВВ для пород V группы: уменьшение не применено.",
            )
        )
        values["rock_group_v_reduce"] = False

    if "hardness_f" in manual:
        values["hardness_f"], sources["hardness_f"] = float(manual["hardness_f"]), "MANUAL_OVERRIDE"
    elif rock and _positive(rock.get("hardness_f")):
        values["hardness_f"], sources["hardness_f"] = float(rock["hardness_f"]), "REFERENCE"
    else:
        values["hardness_f"], sources["hardness_f"] = FORM_DEFAULTS["hardness_f"], "REFERENCE"
        issues.append(
            SafetyIssue(
                "warning",
                "hardness_unknown",
                "Крепость пород f не задана ни у породы блока, ни в проекте: разлёт посчитан при f = 14 (форма v0.11).",
            )
        )

    return SafetyParams(
        **values,
        manual_zones=dict(manual_zones or {}),
        sources=sources,
        issues=tuple(issues),
    )


def _site_payload(site_safety: Mapping[str, Any] | None, issues: list[SafetyIssue]) -> dict[str, Any]:
    """Payload записи объекта с умолчаниями схемы раздела.

    Пустое поле записи — умолчание схемы (IX группа и мороз — «нет»), а не
    формы: запись заведена, значит, объект свои условия указал. Запись, не
    прошедшая схему (опубликована до её изменения), читается как нет записи.
    """

    if site_safety is None:
        return {}
    from cost.v2.schemas.safety import BlastSafetyPayload
    from pydantic import ValidationError

    try:
        model = BlastSafetyPayload.model_validate(dict(site_safety))
    except ValidationError:
        issues.append(
            SafetyIssue(
                "warning",
                "safety_reference_invalid",
                "Запись «Безопасные расстояния и выписка ВМ» объекта не проходит проверку: коэффициенты взяты "
                "по форме ВМ.09.03 v0.11.",
            )
        )
        return {}
    return model.model_dump(mode="python")


_LABELS = {
    "k_ground": "K_г",
    "k_structure": "K_с",
    "alpha_blast": "α",
    "people_min_m": "минимум для людей",
    "k_mech": "доля зоны для механизмов",
    "delay_group_ms": "порог группы замедления",
    "hardness_f": "крепость f",
    "relief_height_m": "превышение блока",
    "slope_angle_deg": "угол косогора",
}

# Ручные числа проекта МВ, которые должны быть больше нуля (угол косогора и
# превышение могут быть нулём — «не косогор», «превышения нет»).
_POSITIVE = (*_NUMBERS, "hardness_f")


def _manual_values(overrides: Mapping[str, Any] | None, issues: list[SafetyIssue]) -> dict[str, Any]:
    """Ручные значения проекта МВ; негодное — предупреждение и значение справочника.

    Пробел или опечатка в проекте не роняют расчёт (как в модели
    себестоимости), а ноль крепости или K_г не дают молча нулевую зону.
    """

    manual: dict[str, Any] = {}
    for name, value in (overrides or {}).items():
        if value is None or value == "":
            continue
        if name in _FLAGS:
            manual[name] = bool(value)
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            number = float("nan")
        bad = not math.isfinite(number) or (number <= 0 if name in _POSITIVE else number < 0)
        if bad:
            issues.append(
                SafetyIssue(
                    "warning",
                    "manual_value_invalid",
                    f"Значение «{value}» ({_LABELS.get(name, name)}) в проекте МВ не годится: взято значение справочника.",
                )
            )
            continue
        manual[name] = number
    return manual


def _coerce(name: str, value: Any) -> Any:
    if name in _FLAGS:
        return bool(value)
    return float(value)


def _positive(value: Any) -> bool:
    try:
        return float(value) > 0
    except (TypeError, ValueError):
        return False


def _table(rows: Any) -> tuple[tuple[float, float], ...]:
    points = sorted((float(row["ratio"]), float(row["k"])) for row in rows)
    return tuple(points)
