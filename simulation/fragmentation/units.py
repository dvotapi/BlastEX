"""Explicit unit conversions for fragmentation formulas.

Callers must opt in. Geometry lengths stay in metres; fragment sizes stay
in millimetres. Rock density from geology is SI (kg/m³); Kuznetsov A uses
t/m³, matching ``Blast.py``.
"""

from __future__ import annotations

KG_PER_T = 1000.0
MM_PER_M = 1000.0
MM_PER_CM = 10.0
# Heat of explosion of TNT used as the RE_weight reference, MJ/kg.
TNT_ENERGY_MJ_KG = 4.184
# Kuznetsov energy index: ANFO = 100, TNT = 115.
KUZNETSOV_TNT_INDEX = 115.0


def density_t_m3_from_kg_m3(density_kg_m3: float) -> float:
    """kg/m³ → t/m³. 1000 kg/m³ = 1 t/m³."""
    return float(density_kg_m3) / KG_PER_T


def density_kg_m3_from_t_m3(density_t_m3: float) -> float:
    """t/m³ → kg/m³."""
    return float(density_t_m3) * KG_PER_T


def length_mm_from_m(length_m: float) -> float:
    """metres → millimetres."""
    return float(length_m) * MM_PER_M


def length_m_from_mm(length_mm: float) -> float:
    """millimetres → metres."""
    return float(length_mm) / MM_PER_M


def fragment_mm_from_cm(size_cm: float) -> float:
    """Kuznetsov historically returns centimetres; convert to millimetres."""
    return float(size_cm) * MM_PER_CM


def relative_weight_strength(energy_mj_kg: float) -> float:
    """TNT-relative weight strength: RE = Q_exp / 4.184 MJ/kg."""
    return float(energy_mj_kg) / TNT_ENERGY_MJ_KG
