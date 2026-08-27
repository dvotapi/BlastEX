"""Build local influence regions from a spatial ``BlastDesign``.

Each enabled hole is one region. Holes that share a designed geological domain
form a domain region. The whole block is the site region.

Rock properties come from designed intervals only. Measured geology is ignored.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from design.editing import local_burden, local_spacing
from design.geology import designed_rock_intervals
from design.models import (
    BlastDesign,
    Hole,
    HoleLoad,
    is_explosive_deck_kind,
)
from design.geometry import true_burden
from simulation.fragmentation.models import FragmentationInputs
from simulation.fragmentation.units import density_t_m3_from_kg_m3, length_m_from_mm

DEFAULT_ROCK_DENSITY_T_M3 = 2.7
DEFAULT_ROCK_UCS_MPA = 120.0
DEFAULT_ROCK_FISSURING = 2.0
DEFAULT_EXPLOSIVE_DENSITY_T_M3 = 0.82
DEFAULT_EXPLOSIVE_ENERGY_MJ_KG = 3.8
DEFAULT_HOLE_OVERSIZE = 1.05


@dataclass
class ExplosiveSpec:
    name: str
    density_t_m3: float
    power_mj_kg: float


@dataclass
class RockSpec:
    name: str
    density_t_m3: float
    ucs_mpa: float
    fissuring_ff: float


@dataclass
class InfluenceRegion:
    id: str
    kind: str  # hole | domain | site
    hole_ids: list[str]
    inputs: FragmentationInputs
    x: float = 0.0
    y: float = 0.0
    hole_kind: str = "production"
    warnings: list[str] = field(default_factory=list)


def _finite(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(parsed):
        return default
    return parsed


def _parse_fissuring(raw: str, fallback: float) -> float:
    text = str(raw or "").strip().replace(",", ".")
    if not text:
        return fallback
    try:
        return float(text)
    except ValueError:
        lowered = text.lower()
        if lowered in {"intense", "high", "weathered"}:
            return max(fallback, 3.0)
        if lowered in {"moderate", "medium", "competent"}:
            return fallback
        if lowered in {"low", "massive"}:
            return min(fallback, 1.0)
        return fallback


def _stemming_m(load: HoleLoad | None, hole: Hole, charge_rules: dict[str, Any]) -> float:
    if load is not None:
        stemming = sum(
            max(0.0, deck.to_m - deck.from_m) for deck in load.decks if deck.kind == "stemming"
        )
        if stemming > 0:
            return stemming
    if charge_rules.get("stemming_m") not in (None, ""):
        return max(0.0, _finite(charge_rules.get("stemming_m"), 0.0))
    stemming_k = _finite(charge_rules.get("stemming_k"), 20.0)
    return max(0.0, min(hole.length_m, stemming_k * length_m_from_mm(hole.diameter_mm)))


def _catalog_lookup(catalog: dict[str, ExplosiveSpec], key: str) -> ExplosiveSpec | None:
    if not key:
        return None
    if key in catalog:
        return catalog[key]
    lowered = key.lower()
    for name, spec in catalog.items():
        if name.lower() == lowered:
            return spec
    return None


def _mass_weighted_explosive(
    load: HoleLoad | None,
    catalog: dict[str, ExplosiveSpec],
    default: ExplosiveSpec,
) -> ExplosiveSpec:
    if load is None:
        return default
    total = 0.0
    density_acc = 0.0
    energy_acc = 0.0
    names: list[str] = []
    for deck in load.decks:
        if not is_explosive_deck_kind(deck.kind) or deck.mass_kg <= 0:
            continue
        spec = _catalog_lookup(catalog, deck.explosive_key or deck.product) or default
        total += deck.mass_kg
        density_acc += spec.density_t_m3 * deck.mass_kg
        energy_acc += spec.power_mj_kg * deck.mass_kg
        if spec.name not in names:
            names.append(spec.name)
    if total <= 0:
        return default
    return ExplosiveSpec(
        name="+".join(names) if names else default.name,
        density_t_m3=density_acc / total,
        power_mj_kg=energy_acc / total,
    )


def _length_weighted_rock(hole: Hole, default: RockSpec) -> RockSpec:
    intervals = designed_rock_intervals(hole)
    if not intervals:
        return default
    total = 0.0
    density_acc = 0.0
    ucs_acc = 0.0
    fiss_acc = 0.0
    names: list[str] = []
    for interval in intervals:
        length = max(0.0, interval.to_m - interval.from_m)
        if length <= 0:
            continue
        props = interval.properties
        density = (
            density_t_m3_from_kg_m3(props.density_kg_m3)
            if props.density_kg_m3
            else default.density_t_m3
        )
        ucs = props.ucs_mpa if props.ucs_mpa else default.ucs_mpa
        fiss = _parse_fissuring(props.fracturing, default.fissuring_ff)
        total += length
        density_acc += density * length
        ucs_acc += ucs * length
        fiss_acc += fiss * length
        label = interval.domain_name or interval.domain_id
        if label and label not in names:
            names.append(label)
    if total <= 0:
        return default
    return RockSpec(
        name="+".join(names) if names else default.name,
        density_t_m3=density_acc / total,
        ucs_mpa=ucs_acc / total,
        fissuring_ff=fiss_acc / total,
    )


def _primary_domain_id(hole: Hole) -> str:
    intervals = designed_rock_intervals(hole)
    if not intervals:
        return ""
    longest = max(intervals, key=lambda item: max(0.0, item.to_m - item.from_m))
    return longest.domain_id or longest.domain_name or ""


def _estimate_charge_kg(
    hole: Hole,
    stemming_m: float,
    explosive: ExplosiveSpec,
    hole_oversize_coeff: float,
) -> float:
    """Linear capacity × charge length. Density t/m³ → kg via ×1000."""
    diameter_m = length_m_from_mm(hole.diameter_mm) * hole_oversize_coeff
    capacity_kg_per_m = math.pi * (diameter_m**2) / 4.0 * explosive.density_t_m3 * 1000.0
    charge_length = max(0.0, hole.length_m - stemming_m)
    return capacity_kg_per_m * charge_length


def _influence_volume_m3(burden_m: float, spacing_m: float, bench_height_m: float, load: HoleLoad | None) -> float:
    if load is not None and load.influence_volume_m3 > 0:
        return load.influence_volume_m3
    return max(0.0, burden_m) * max(0.0, spacing_m) * max(0.0, bench_height_m)


def collect_hole_regions(
    design: BlastDesign,
    *,
    lump_size_mm: float,
    default_rock: RockSpec,
    default_explosive: ExplosiveSpec,
    explosives: dict[str, ExplosiveSpec] | None = None,
    hole_oversize_coeff: float | None = None,
) -> list[InfluenceRegion]:
    """One influence region per enabled hole with enough inputs to predict."""
    catalog = dict(explosives or {})
    catalog.setdefault(default_explosive.name, default_explosive)
    rules = dict(design.charge_rules or {})
    pattern = dict(design.pattern_params or {})
    oversize = hole_oversize_coeff
    if oversize is None:
        oversize = _finite(rules.get("hole_oversize_coeff"), DEFAULT_HOLE_OVERSIZE)
    loads = {load.hole_id: load for load in design.loads}
    enabled = [hole for hole in design.holes if hole.enabled]
    fallback_spacing = _finite(pattern.get("spacing_a_m"), _finite(rules.get("grid_a_m"), 0.0))
    fallback_burden = _finite(pattern.get("burden_b_m"), _finite(rules.get("grid_b_m"), 0.0))

    regions: list[InfluenceRegion] = []
    for hole in enabled:
        load = loads.get(hole.id)
        warnings: list[str] = []
        burden = local_burden(enabled, hole, design.contour)
        if burden is None:
            burden = true_burden(hole, design.contour)
        if burden is None or burden <= 0:
            burden = fallback_burden
            if burden <= 0:
                warnings.append("Нет локальной ЛНС — скважина пропущена.")
                continue
        spacing = local_spacing(enabled, hole)
        if spacing is None or spacing <= 0:
            spacing = fallback_spacing
            if spacing <= 0:
                warnings.append("Нет локального шага — скважина пропущена.")
                continue

        rock = _length_weighted_rock(hole, default_rock)
        explosive = _mass_weighted_explosive(load, catalog, default_explosive)
        stemming = _stemming_m(load, hole, rules)
        charge_mass = load.total_charge_kg if load is not None else 0.0
        if charge_mass <= 0:
            charge_mass = _estimate_charge_kg(hole, stemming, explosive, oversize)
            if charge_mass <= 0:
                warnings.append("Нет массы заряда — скважина пропущена.")
                continue
            warnings.append("Масса заряда оценена по диаметру и плотности ВВ (нет дек).")

        volume = _influence_volume_m3(burden, spacing, hole.bench_height_m, load)
        if load is not None and load.specific_q_kg_m3 > 0:
            powder_factor = load.specific_q_kg_m3
            if volume <= 0:
                volume = charge_mass / powder_factor if powder_factor > 0 else 0.0
        else:
            if volume <= 0:
                warnings.append("Нулевой объём влияния — скважина пропущена.")
                continue
            powder_factor = charge_mass / volume

        inputs = FragmentationInputs(
            burden_m=burden,
            spacing_m=spacing,
            bench_height_m=hole.bench_height_m,
            diameter_mm=hole.diameter_mm,
            charge_mass_kg=charge_mass,
            powder_factor_kg_m3=powder_factor,
            stemming_m=stemming,
            explosive_name=explosive.name,
            explosive_density_t_m3=explosive.density_t_m3,
            explosive_energy_mj_kg=explosive.power_mj_kg,
            rock_name=rock.name or default_rock.name,
            rock_density_t_m3=rock.density_t_m3,
            rock_ucs_mpa=rock.ucs_mpa,
            rock_fissuring=rock.fissuring_ff,
            lump_size_mm=lump_size_mm,
            hole_oversize_coeff=oversize,
            influence_volume_m3=volume,
        )
        regions.append(
            InfluenceRegion(
                id=f"hole:{hole.id}",
                kind="hole",
                hole_ids=[hole.id],
                inputs=inputs,
                x=hole.collar.x,
                y=hole.collar.y,
                hole_kind=hole.kind,
                warnings=warnings,
            )
        )
    return regions


def _weighted_mean(values: list[tuple[float, float]]) -> float:
    weight = sum(item[1] for item in values)
    if weight <= 0:
        return 0.0
    return sum(value * w for value, w in values) / weight


def aggregate_region(
    region_id: str,
    kind: str,
    members: list[InfluenceRegion],
    lump_size_mm: float,
) -> InfluenceRegion | None:
    if not members:
        return None
    weights = [max(item.inputs.influence_volume_m3, item.inputs.charge_mass_kg, 1e-9) for item in members]
    pairs = list(zip(members, weights))

    def avg(getter) -> float:
        return _weighted_mean([(getter(item.inputs), w) for item, w in pairs])

    charge_total = sum(item.inputs.charge_mass_kg for item in members)
    volume = sum(item.inputs.influence_volume_m3 for item in members)
    powder = charge_total / volume if volume > 0 else avg(lambda inp: inp.powder_factor_kg_m3)
    # Kuznetsov Q is charge mass of one hole, not the whole blast.
    mean_charge = avg(lambda inp: inp.charge_mass_kg)
    names = []
    for item in members:
        if item.inputs.rock_name and item.inputs.rock_name not in names:
            names.append(item.inputs.rock_name)
    expl_names = []
    for item in members:
        if item.inputs.explosive_name and item.inputs.explosive_name not in expl_names:
            expl_names.append(item.inputs.explosive_name)
    template = members[0].inputs
    inputs = FragmentationInputs(
        burden_m=avg(lambda inp: inp.burden_m),
        spacing_m=avg(lambda inp: inp.spacing_m),
        bench_height_m=avg(lambda inp: inp.bench_height_m),
        diameter_mm=avg(lambda inp: inp.diameter_mm),
        charge_mass_kg=mean_charge,
        powder_factor_kg_m3=powder,
        stemming_m=avg(lambda inp: inp.stemming_m),
        explosive_name="+".join(expl_names) if expl_names else template.explosive_name,
        explosive_density_t_m3=avg(lambda inp: inp.explosive_density_t_m3),
        explosive_energy_mj_kg=avg(lambda inp: inp.explosive_energy_mj_kg),
        rock_name="+".join(names) if names else template.rock_name,
        rock_density_t_m3=avg(lambda inp: inp.rock_density_t_m3),
        rock_ucs_mpa=avg(lambda inp: inp.rock_ucs_mpa),
        rock_fissuring=avg(lambda inp: inp.rock_fissuring),
        lump_size_mm=lump_size_mm,
        hole_oversize_coeff=template.hole_oversize_coeff,
        influence_volume_m3=volume,
    )
    xs = [item.x for item in members]
    ys = [item.y for item in members]
    return InfluenceRegion(
        id=region_id,
        kind=kind,
        hole_ids=[hid for item in members for hid in item.hole_ids],
        inputs=inputs,
        x=sum(xs) / len(xs),
        y=sum(ys) / len(ys),
        hole_kind=kind,
    )


def collect_regions(
    design: BlastDesign,
    *,
    lump_size_mm: float,
    default_rock: RockSpec,
    default_explosive: ExplosiveSpec,
    explosives: dict[str, ExplosiveSpec] | None = None,
    hole_oversize_coeff: float | None = None,
) -> tuple[list[InfluenceRegion], list[InfluenceRegion], InfluenceRegion | None, list[str]]:
    """Hole regions, domain regions, site region, and skip warnings."""
    holes = collect_hole_regions(
        design,
        lump_size_mm=lump_size_mm,
        default_rock=default_rock,
        default_explosive=default_explosive,
        explosives=explosives,
        hole_oversize_coeff=hole_oversize_coeff,
    )
    warnings = [msg for region in holes for msg in region.warnings]
    enabled_ids = {hole.id for hole in design.holes if hole.enabled}
    skipped = enabled_ids - {hid for region in holes for hid in region.hole_ids}
    if skipped:
        warnings.append(f"Пропущено скважин без входов: {len(skipped)}.")

    by_domain: dict[str, list[InfluenceRegion]] = {}
    hole_by_id = {hole.id: hole for hole in design.holes}
    for region in holes:
        hole = hole_by_id.get(region.hole_ids[0])
        domain_id = _primary_domain_id(hole) if hole is not None else ""
        key = domain_id or "unassigned"
        by_domain.setdefault(key, []).append(region)

    domains: list[InfluenceRegion] = []
    for domain_id, members in by_domain.items():
        aggregated = aggregate_region(f"domain:{domain_id}", "domain", members, lump_size_mm)
        if aggregated is not None:
            domains.append(aggregated)

    site = aggregate_region("site", "site", holes, lump_size_mm)
    return holes, domains, site, warnings
