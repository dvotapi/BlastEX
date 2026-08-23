"""Explicit unit conversions for the blast passport.

Callers must opt in. Geometry stays in metres. Fragment sizes stay in
millimetres. Charge mass stays in kilograms. PPV stays in mm/s. Cost stays
in roubles. Diameter arrives in millimetres and is never treated as metres.
"""
from __future__ import annotations

KG_PER_T = 1000.0
MM_PER_M = 1000.0
MS_PER_S = 1000.0


def length_m_from_mm(length_mm: float) -> float:
    """millimetres → metres."""
    return float(length_mm) / MM_PER_M


def length_mm_from_m(length_m: float) -> float:
    """metres → millimetres."""
    return float(length_m) * MM_PER_M


def mass_kg_from_t(mass_t: float) -> float:
    """tonnes → kilograms."""
    return float(mass_t) * KG_PER_T


def mass_t_from_kg(mass_kg: float) -> float:
    """kilograms → tonnes."""
    return float(mass_kg) / KG_PER_T


def time_s_from_ms(time_ms: float) -> float:
    """milliseconds → seconds."""
    return float(time_ms) / MS_PER_S


def time_ms_from_s(time_s: float) -> float:
    """seconds → milliseconds."""
    return float(time_s) * MS_PER_S
