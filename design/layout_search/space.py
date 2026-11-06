"""Пространство вариантов перебора раскладки: три этапа от грубого к точному.

Шаблонов два: от бровки (нет ключа `layout_anchor`) и «от тыла»
(`layout_anchor = "back"`, `design/back_layout.py`; только квадратная и
прямоугольная сетки, нужны тыл и свободная поверхность).

Этап 1 — азимут рядов, сдвиги сетки и фланг вруба (у «от тыла» — поворот
около азимута тыла, отступ от тыла и сдвиг вдоль ряда); этап 2 — схема первого
ряда у откоса для лучших семян от бровки («от тыла» схем первого ряда нет:
конец эшелона генератор выводит сам); этап 3 — тонкая подстройка вокруг лучших
семян (азимут, сдвиги, шаги a и b в пределах ±3 % от базовых; у переменной
сетки и сетки по доменам шаги не перебираются; у «от тыла» шаги — при
геометрии семени). Каждый этап удаляет дубли по `Candidate.key()`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from design.back_layout import BACK_OFFSET_RANGE, back_azimuth_deg, back_side
from design.geometry import crest_azimuth_deg
from design.models import BlockContour
from design.pattern import LAYOUT_ANCHOR_BACK, LAYOUT_ANCHOR_PATTERNS, PATTERN_TYPES
from design.toe_line import grid_steps_m, min_crest_offset_m

FLANKS = ("left", "right")
# Этап 1: азимут опорный + k·2,5°, k = −4…4 (то есть ±10°).
AZIMUTH_STEP_DEG = 2.5
AZIMUTH_STEPS = range(-4, 5)
# Этап 3: подстройка азимута вокруг семени.
FINE_AZIMUTH_DEG = 1.25
# Этап 3: множители шагов сетки (±3 %).
STEP_MULTIPLIERS = (0.97, 1.0, 1.03)
# Этап 2: параметры схем первого ряда. Пара одна: устье генератор сдвигает к
# кромке, угол — наименьший до ЛСП ≈ W (решение владельца 06.11.2026), так что
# разные `front_rows_tilt_deg` > 0 дают одну раскладку.
PAIR_TILTS_DEG = (15,)
TAPER_COUNTS = (1, 2)
TAPER_TILTS_DEG = (15, 30)
FRONT_ROW_KEYS = ("front_rows_mode", "front_rows_tilt_count", "front_rows_tilt_deg")
# Шаблон «от тыла»: ключи опоры и отступа от тыла.
BACK_ANCHOR_KEYS = ("layout_anchor", "back_offset_m")
# Этап 1 «от тыла»: поворот около азимута тыла (±5°, шаг 2,5°; этап 3 —
# ±1,25° внутри тех же ±5°) и отступ приконтурного ряда — доли b в рабочем
# диапазоне 0,5–0,8·b (`back_layout.BACK_OFFSET_RANGE`).
BACK_TURNS_DEG = (-5.0, -2.5, 0.0, 2.5, 5.0)
BACK_TURN_LIMIT_DEG = 5.0
# Допуск предела поворота: азимут варианта округлён до 0,0001° (`_azimuth`),
# и семя на краю (±5°) читается как 5,00003° — без допуска его подстройка терялась.
BACK_TURN_TOLERANCE_DEG = 1e-3
BACK_OFFSET_RATIOS = (0.5, 0.6, 0.7, 0.8)
# Этап 3 «от тыла»: подстройка отступа, доля b.
BACK_FINE_OFFSET_RATIO = 0.05
# Ключи, которыми перебор управляет сам; из базы они убираются.
_OWN_KEYS = ("first_row_burden_m", "grid_shift_along_m", "offset_from_face_m", *FRONT_ROW_KEYS, *BACK_ANCHOR_KEYS)


@dataclass(frozen=True)
class Candidate:
    """Вариант раскладки: полный `pattern_params` и фланг вруба."""

    params: dict[str, Any]
    cut_flank: str

    def key(self) -> tuple:
        """Ключ дедупликации: отсортированные пары params (числа до 0,01) и фланг."""
        pairs = []
        for name in sorted(self.params):
            value = self.params[name]
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                value = round(float(value), 2) + 0.0  # + 0.0 убирает «-0.0»
            else:
                value = repr(value)
            pairs.append((name, value))
        return (tuple(pairs), self.cut_flank)


def is_back(params: dict) -> bool:
    """Вариант шаблона «от тыла»."""
    return params.get("layout_anchor") == LAYOUT_ANCHOR_BACK


def back_applicable(base: dict, contour: BlockContour) -> bool:
    """Шаблон «от тыла» перебирается: квадратная или прямоугольная сетка (вид —
    как у генератора: неизвестный или без ключа — квадратная), есть тыл и
    свободная поверхность (без неё эшелонам не к чему идти)."""
    pattern = str(base.get("pattern", "square"))
    if pattern not in PATTERN_TYPES:
        pattern = "square"
    return pattern in LAYOUT_ANCHOR_PATTERNS and bool(contour.free_faces) and back_side(contour) is not None


def interleave_templates(items: list[Candidate]) -> list[Candidate]:
    """Варианты двух шаблонов через один (от бровки, «от тыла», …), остаток —
    в конце: кончится бюджет посреди этапа — оба шаблона просчитаны поровну."""
    crest = [c for c in items if not is_back(c.params)]
    back = [c for c in items if is_back(c.params)]
    out: list[Candidate] = []
    for k in range(max(len(crest), len(back))):
        out.extend(group[k] for group in (crest, back) if k < len(group))
    return out


def _turn(azimuth: float, ref: float) -> float:
    """Поворот азимута рядов от опорного в (−180; 180]."""
    return (azimuth - ref + 180.0) % 360.0 - 180.0


def _dedup(items: list[Candidate]) -> list[Candidate]:
    seen: set[tuple] = set()
    out: list[Candidate] = []
    for item in items:
        k = item.key()
        if k not in seen:
            seen.add(k)
            out.append(item)
    return out


def _own_steps(params: dict) -> bool:
    """Шаги берутся из строк `row_params` или доменов — множители общих a и b не действуют."""
    return str(params.get("pattern", "square")) in ("variable", "domain_dependent")


def _is_square(params: dict) -> bool:
    """Квадратная ли сетка (a == b): как в `toe_line` — нет ключа или неизвестный вид."""
    return str(params.get("pattern", "square")) not in ("rectangular", "staggered", "variable", "domain_dependent")


def _azimuth(value: float) -> float:
    """Азимут в [0; 360) до 0,0001°: после округления ещё раз `% 360` — 359,99999 даёт 0, а не 360."""
    return round(value % 360.0, 4) % 360.0 + 0.0


def _with_shift(params: dict, shift: float) -> dict:
    """Сдвиг вдоль ряда пишется только когда не 0 (иначе сетка прежняя)."""
    out = {k: v for k, v in params.items() if k != "grid_shift_along_m"}
    shift = round(shift, 4)
    if abs(shift) > 1e-9:
        out["grid_shift_along_m"] = shift
    return out


def stage1(base: dict, contour: BlockContour) -> list[Candidate]:
    """Этап 1: варианты от бровки (288), затем «от тыла» (160), если шаблон применим."""
    out = _crest_stage1(base, contour)
    if back_applicable(base, contour):
        out += _back_stage1(base, contour)
    return _dedup(out)


def _back_stage1(base: dict, contour: BlockContour) -> list[Candidate]:
    """«От тыла»: поворот около азимута тыла × отступ от тыла × сдвиг вдоль × фланг
    (5 × 4 × 4 × 2 = 160). Схем первого ряда нет, `offset_from_face_m` не пишется;
    `front_rows_tilt_deg` базы (предел наклона конца эшелона) сохраняется."""
    ref = back_azimuth_deg(contour)
    if ref is None:
        return []
    a, b = grid_steps_m(base)
    plain = {k: v for k, v in base.items() if k not in _OWN_KEYS}
    # `front_rows_tilt_deg` у «от тыла» — предел наклона конца эшелона (0 — без
    # наклона), а не угол схемы первого ряда: он берётся из базы.
    if "front_rows_tilt_deg" in base:
        plain["front_rows_tilt_deg"] = base["front_rows_tilt_deg"]
    out: list[Candidate] = []
    for turn in BACK_TURNS_DEG:
        az = _azimuth(ref + turn)
        for ratio in BACK_OFFSET_RATIOS:
            for ks in range(4):
                params = _with_shift(dict(plain), ks * a / 4.0)
                params["row_azimuth_deg"] = az
                params["layout_anchor"] = LAYOUT_ANCHOR_BACK
                params["back_offset_m"] = round(ratio * b, 4)
                for flank in FLANKS:
                    out.append(Candidate(dict(params), flank))
    return out


def _crest_stage1(base: dict, contour: BlockContour) -> list[Candidate]:
    """От бровки: азимут × сдвиг вдоль × сдвиг поперёк × фланг (288 вариантов)."""
    ref = crest_azimuth_deg(contour)
    if ref is None:
        try:
            ref = float(base.get("row_azimuth_deg") or 0.0)
        except (TypeError, ValueError):
            ref = 0.0
    a, b = grid_steps_m(base)
    o0 = min_crest_offset_m(base)
    plain = {k: v for k, v in base.items() if k not in _OWN_KEYS}
    out: list[Candidate] = []
    for ka in AZIMUTH_STEPS:
        az = _azimuth(ref + ka * AZIMUTH_STEP_DEG)
        for ks in range(4):
            for ko in range(4):
                params = _with_shift(dict(plain), ks * a / 4.0)
                params["row_azimuth_deg"] = az
                params["offset_from_face_m"] = round(o0 + ko * b / 4.0, 4)
                for flank in FLANKS:
                    out.append(Candidate(dict(params), flank))
    return out


def stage2(seeds: list[Candidate], base: dict) -> list[Candidate]:
    """Этап 2: для каждого семени — оно само, 4 пары и 4 перехода (у шахматки без
    переходов); у семени «от тыла» — только оно само (схем первого ряда нет)."""
    out: list[Candidate] = []
    for seed in seeds:
        if is_back(seed.params):
            out.append(seed)
            continue
        clean = {k: v for k, v in seed.params.items() if k not in FRONT_ROW_KEYS}
        out.append(seed)
        for tilt in PAIR_TILTS_DEG:
            out.append(Candidate(
                {**clean, "front_rows_mode": "pair", "front_rows_tilt_count": 1, "front_rows_tilt_deg": tilt},
                seed.cut_flank,
            ))
        if clean.get("pattern") == "staggered":
            continue
        for count in TAPER_COUNTS:
            for tilt in TAPER_TILTS_DEG:
                out.append(Candidate(
                    {**clean, "front_rows_mode": "taper", "front_rows_tilt_count": count, "front_rows_tilt_deg": tilt},
                    seed.cut_flank,
                ))
    return _dedup(out)


def stage3(seeds: list[Candidate], base: dict, contour: BlockContour | None = None) -> list[Candidate]:
    """Этап 3: подстройка вокруг семян — азимут ±1,25°, сдвиги ±a/8 и ±b/8, шаги ×{0,97; 1; 1,03}
    (у переменной сетки и сетки по доменам шаги не трогаются). Семя «от тыла» —
    `_back_stage3` (поворот держится в ±5° от тыла, если задан `contour`)."""
    crest = [seed for seed in seeds if not is_back(seed.params)]
    back = [seed for seed in seeds if is_back(seed.params)]
    out = _crest_stage3(crest, base)
    if back:
        ref = back_azimuth_deg(contour) if contour is not None else None
        out += _back_stage3(back, base, ref)
    return _dedup(out)


def _back_stage3(seeds: list[Candidate], base: dict, ref: float | None) -> list[Candidate]:
    """«От тыла»: геометрия (поворот ±1,25°, сдвиг ±a/8, отступ ±0,05·b) — 27
    вариантов, и шаги a и b ×{0,97; 1; 1,03} при геометрии семени — ещё 8 (у
    квадратной — 2). Шаги не перемножаются с геометрией: генерация «от тыла»
    в 4–8 раз дольше, чем от бровки, и полное произведение (243 на семя) не
    уложилось бы в общий бюджет. Поворот — в ±5° от азимута тыла `ref`,
    отступ — в 0,5–0,8·b (b — базовый)."""
    a0, b0 = grid_steps_m(base)
    square = _is_square(base)
    lo, hi = BACK_OFFSET_RANGE[0] * b0, BACK_OFFSET_RANGE[1] * b0
    mults_b = (1.0,) if square else STEP_MULTIPLIERS
    out: list[Candidate] = []
    for seed in seeds:
        p = seed.params
        az0 = float(p.get("row_azimuth_deg", 0.0) or 0.0)
        sh0 = float(p.get("grid_shift_along_m", 0.0) or 0.0)
        of0 = float(p.get("back_offset_m", 0.65 * b0) or 0.65 * b0)
        for daz in (-FINE_AZIMUTH_DEG, 0.0, FINE_AZIMUTH_DEG):
            az = az0 + daz
            if ref is not None and abs(_turn(az, ref)) > BACK_TURN_LIMIT_DEG + BACK_TURN_TOLERANCE_DEG:
                continue
            for dsh in (-a0 / 8.0, 0.0, a0 / 8.0):
                for dof in (-BACK_FINE_OFFSET_RATIO * b0, 0.0, BACK_FINE_OFFSET_RATIO * b0):
                    params = _with_shift(dict(p), sh0 + dsh)
                    params["row_azimuth_deg"] = _azimuth(az)
                    params["back_offset_m"] = round(min(hi, max(lo, of0 + dof)), 4)
                    out.append(Candidate(params, seed.cut_flank))
        for ma in STEP_MULTIPLIERS:
            for mb in mults_b:
                params = dict(p)
                params["spacing_a_m"] = round(a0 * ma, 4)
                if not square:
                    params["burden_b_m"] = round(b0 * mb, 4)
                out.append(Candidate(params, seed.cut_flank))
    return out


def _crest_stage3(seeds: list[Candidate], base: dict) -> list[Candidate]:
    """От бровки: азимут ±1,25°, сдвиги ±a/8 и ±b/8, шаги ×{0,97; 1; 1,03}."""
    a0, b0 = grid_steps_m(base)
    o0 = min_crest_offset_m(base)
    square = _is_square(base)
    # Переменная сетка и сетка по доменам: шаги не перебираются (множитель 1).
    fixed = _own_steps(base)
    mults_a = (1.0,) if fixed else STEP_MULTIPLIERS
    mults_b = (1.0,) if square or fixed else STEP_MULTIPLIERS
    out: list[Candidate] = []
    for seed in seeds:
        p = seed.params
        az0 = float(p.get("row_azimuth_deg", base.get("row_azimuth_deg") or 0.0) or 0.0)
        sh0 = float(p.get("grid_shift_along_m", 0.0) or 0.0)
        of0 = float(p.get("offset_from_face_m", o0))
        for daz in (-FINE_AZIMUTH_DEG, 0.0, FINE_AZIMUTH_DEG):
            for dsh in (-a0 / 8.0, 0.0, a0 / 8.0):
                for dof in (-b0 / 8.0, 0.0, b0 / 8.0):
                    for ma in mults_a:
                        for mb in mults_b:
                            params = _with_shift(dict(p), sh0 + dsh)
                            params["row_azimuth_deg"] = _azimuth(az0 + daz)
                            params["offset_from_face_m"] = round(max(o0, of0 + dof), 4)
                            if not fixed:
                                params["spacing_a_m"] = round(a0 * ma, 4)
                            if not square and not fixed:
                                params["burden_b_m"] = round(b0 * mb, 4)
                            out.append(Candidate(params, seed.cut_flank))
    return out
