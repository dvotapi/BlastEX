"""Пространство вариантов перебора раскладки: три этапа от грубого к точному.

Этап 1 — азимут рядов, сдвиги сетки и фланг вруба; этап 2 — схема первого ряда
у откоса для лучших семян; этап 3 — тонкая подстройка вокруг лучших семян
(азимут, сдвиги, шаги a и b в пределах ±3 % от базовых). Каждый этап удаляет
дубли по `Candidate.key()`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from design.geometry import crest_azimuth_deg
from design.models import BlockContour
from design.toe_line import grid_steps_m, min_crest_offset_m

FLANKS = ("left", "right")
# Этап 1: азимут опорный + k·2,5°, k = −4…4 (то есть ±10°).
AZIMUTH_STEP_DEG = 2.5
AZIMUTH_STEPS = range(-4, 5)
# Этап 3: подстройка азимута вокруг семени.
FINE_AZIMUTH_DEG = 1.25
# Этап 3: множители шагов сетки (±3 %).
STEP_MULTIPLIERS = (0.97, 1.0, 1.03)
# Этап 2: параметры схем первого ряда.
PAIR_TILTS_DEG = (15, 20, 25, 30)
TAPER_COUNTS = (1, 2)
TAPER_TILTS_DEG = (15, 30)
FRONT_ROW_KEYS = ("front_rows_mode", "front_rows_tilt_count", "front_rows_tilt_deg")
# Ключи, которыми перебор управляет сам; из базы они убираются.
_OWN_KEYS = ("first_row_burden_m", "grid_shift_along_m", "offset_from_face_m", *FRONT_ROW_KEYS)


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


def _dedup(items: list[Candidate]) -> list[Candidate]:
    seen: set[tuple] = set()
    out: list[Candidate] = []
    for item in items:
        k = item.key()
        if k not in seen:
            seen.add(k)
            out.append(item)
    return out


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
    """Этап 1: азимут × сдвиг вдоль × сдвиг поперёк × фланг (288 вариантов)."""
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
    return _dedup(out)


def stage2(seeds: list[Candidate], base: dict) -> list[Candidate]:
    """Этап 2: для каждого семени — оно само, 4 пары и 4 перехода (у шахматки без переходов)."""
    out: list[Candidate] = []
    for seed in seeds:
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


def stage3(seeds: list[Candidate], base: dict) -> list[Candidate]:
    """Этап 3: подстройка вокруг семян — азимут ±1,25°, сдвиги ±a/8 и ±b/8, шаги ×{0,97; 1; 1,03}."""
    a0, b0 = grid_steps_m(base)
    o0 = min_crest_offset_m(base)
    square = _is_square(base)
    mults_b = (1.0,) if square else STEP_MULTIPLIERS
    out: list[Candidate] = []
    for seed in seeds:
        p = seed.params
        az0 = float(p.get("row_azimuth_deg", base.get("row_azimuth_deg") or 0.0) or 0.0)
        sh0 = float(p.get("grid_shift_along_m", 0.0) or 0.0)
        of0 = float(p.get("offset_from_face_m", o0))
        for daz in (-FINE_AZIMUTH_DEG, 0.0, FINE_AZIMUTH_DEG):
            for dsh in (-a0 / 8.0, 0.0, a0 / 8.0):
                for dof in (-b0 / 8.0, 0.0, b0 / 8.0):
                    for ma in STEP_MULTIPLIERS:
                        for mb in mults_b:
                            params = _with_shift(dict(p), sh0 + dsh)
                            params["row_azimuth_deg"] = _azimuth(az0 + daz)
                            params["offset_from_face_m"] = round(max(o0, of0 + dof), 4)
                            params["spacing_a_m"] = round(a0 * ma, 4)
                            if not square:
                                params["burden_b_m"] = round(b0 * mb, 4)
                            out.append(Candidate(params, seed.cut_flank))
    return _dedup(out)
