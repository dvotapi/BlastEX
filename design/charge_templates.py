"""Spatial charge-template engine (phase BDX-004).

Templates are stored on ``BlastDesign.charge_rules["templates"]``. They are
applied in a deterministic order (priority desc, id asc). Higher-priority
matches claim a slice first; later templates fill what is left.

When no templates are present, ``design.charging.apply_charge_rules`` keeps
the previous simple stemming / continuous / spaced behaviour.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Iterable

from Blast import ExplosiveProperties
from cost.geometry import charge_diameter_m, linear_capacity_kg_per_m
from design.editing import local_burden, local_spacing
from design.geology import designed_rock_intervals, designed_water_intervals
from design.geometry import true_burden
from design.models import (
    BlockContour,
    ChargeAction,
    ChargeCondition,
    ChargeTemplate,
    Deck,
    Hole,
    HoleLoad,
    Primer,
    is_explosive_deck_kind,
    sort_templates,
    templates_from_rules,
)

_EPS = 1e-9
_LENGTH_EPS = 1e-6
WET_WATER = frozenset({"wet", "flowing"})


@dataclass(frozen=True)
class HoleChargeContext:
    """Hole-level numbers a template condition can test."""

    kind: str
    row: int
    depth_m: float
    diameter_mm: float
    burden_m: float | None
    spacing_m: float | None
    distance_to_face_m: float | None
    target_pf: float | None


@dataclass
class HoleSlice:
    """One along-hole interval with designed geology / water / region tag."""

    from_m: float
    to_m: float
    domain_id: str = ""
    domain_name: str = ""
    water: str = "dry"
    interval_tag: str = "column"  # collar | column | bottom


@dataclass
class ClaimedSpan:
    from_m: float
    to_m: float
    action: ChargeAction
    template_id: str


def example_wet_dry_bottom_templates() -> list[ChargeTemplate]:
    """The BDX-004 example: bottom emulsion / dry ANFO / wet emulsion."""
    return [
        ChargeTemplate.from_dict(
            {
                "id": "T-bottom",
                "name": "Дно — плотная эмульсия",
                "priority": 30,
                "notes": "Нижняя часть скважины: высокое давление, плотная эмульсия",
                "conditions": {"geological_interval": "bottom"},
                "actions": [
                    {
                        "kind": "bulk_explosive",
                        "explosive_key": "Эмульсия плотная",
                        "region": "bottom",
                        "length_m": 2.0,
                        "place_primer": True,
                    }
                ],
            }
        ),
        ChargeTemplate.from_dict(
            {
                "id": "T-wet",
                "name": "Обводнение — водоустойчивая эмульсия",
                "priority": 20,
                "notes": "Мокрый интервал нельзя заряжать АНФО",
                "conditions": {"water": "wet"},
                "actions": [
                    {
                        "kind": "bulk_explosive",
                        "explosive_key": "Эмульсия водоустойчивая",
                        "region": "interval",
                        "place_primer": True,
                    }
                ],
            }
        ),
        ChargeTemplate.from_dict(
            {
                "id": "T-dry",
                "name": "Сухая колонна — АНФО",
                "priority": 10,
                "notes": "Сухой столб между забойкой и дном",
                "conditions": {"water": "dry"},
                "actions": [
                    {
                        "kind": "bulk_explosive",
                        "explosive_key": "АНФО",
                        "region": "interval",
                    }
                ],
            }
        ),
    ]


def build_hole_context(
    hole: Hole,
    holes: list[Hole],
    rules: dict[str, Any],
    contour: BlockContour | None,
    explosive: ExplosiveProperties,
) -> HoleChargeContext:
    burden = None
    spacing = local_spacing(holes, hole)
    distance_to_face = None
    if contour is not None:
        burden = local_burden(holes, hole, contour)
        distance_to_face = true_burden(hole, contour)
        if burden is None:
            burden = distance_to_face

    grid_a = float(rules.get("grid_a_m") or 0.0)
    grid_b = float(rules.get("grid_b_m") or 0.0)
    target_pf = _opt_rule_float(rules, "target_pf")
    if target_pf is None and grid_a > 0 and grid_b > 0 and hole.bench_height_m > 0:
        volume = grid_a * grid_b * hole.bench_height_m
        stemming = _stemming_from_rules(hole, rules)
        charge_len = max(0.0, hole.length_m - stemming)
        diameter = charge_diameter_m(hole.diameter_mm, float(rules.get("hole_oversize_coeff", 1.05)))
        capacity = linear_capacity_kg_per_m(diameter, explosive.density_t_m3)
        target_pf = (charge_len * capacity) / volume if volume > 0 else None

    return HoleChargeContext(
        kind=hole.kind,
        row=hole.row,
        depth_m=hole.length_m,
        diameter_mm=hole.diameter_mm,
        burden_m=burden,
        spacing_m=spacing,
        distance_to_face_m=distance_to_face,
        target_pf=target_pf,
    )


def _opt_rule_float(rules: dict[str, Any], key: str) -> float | None:
    raw = rules.get(key)
    if raw is None or raw == "":
        return None
    return float(raw)


def _stemming_from_rules(hole: Hole, rules: dict[str, Any]) -> float:
    diameter_m = hole.diameter_mm / 1000.0
    if rules.get("stemming_m") is not None and rules.get("stemming_m") != "":
        stemming = float(rules["stemming_m"])
    else:
        stemming = float(rules.get("stemming_k", 20.0)) * diameter_m
    return max(0.0, min(stemming, hole.length_m))


def _bottom_length(rules: dict[str, Any], templates: list[ChargeTemplate]) -> float:
    explicit = _opt_rule_float(rules, "bottom_length_m")
    if explicit is not None:
        return max(0.0, explicit)
    for template in sort_templates(templates):
        if not template.enabled:
            continue
        if template.conditions.geological_interval != "bottom":
            continue
        for action in template.actions:
            if action.region == "bottom" and action.length_m is not None:
                return max(0.0, action.length_m)
    return 2.0


def _covering_rock(hole: Hole, along_m: float) -> tuple[str, str]:
    for interval in designed_rock_intervals(hole):
        if interval.from_m - _EPS <= along_m <= interval.to_m + _EPS:
            return interval.domain_id, interval.domain_name
    return "", ""


def _covering_water(hole: Hole, along_m: float) -> str:
    for interval in designed_water_intervals(hole):
        if interval.from_m - _EPS <= along_m <= interval.to_m + _EPS:
            return interval.condition or "wet"
    return "dry"


def build_slices(hole: Hole, stemming_m: float, bottom_length_m: float) -> list[HoleSlice]:
    """Split the hole at geology, water, stemming and bottom boundaries."""
    length = hole.length_m
    if length <= _LENGTH_EPS:
        return []

    cuts: set[float] = {0.0, length}
    if stemming_m > _EPS:
        cuts.add(min(length, stemming_m))
    if bottom_length_m > _EPS:
        cuts.add(max(0.0, length - bottom_length_m))
    for interval in designed_rock_intervals(hole):
        cuts.add(max(0.0, min(length, interval.from_m)))
        cuts.add(max(0.0, min(length, interval.to_m)))
    for interval in designed_water_intervals(hole):
        cuts.add(max(0.0, min(length, interval.from_m)))
        cuts.add(max(0.0, min(length, interval.to_m)))

    ordered: list[float] = []
    for value in sorted(cuts):
        if not ordered or abs(value - ordered[-1]) > _LENGTH_EPS:
            ordered.append(value)

    slices: list[HoleSlice] = []
    for start, end in zip(ordered, ordered[1:]):
        if end - start <= _LENGTH_EPS:
            continue
        mid = 0.5 * (start + end)
        domain_id, domain_name = _covering_rock(hole, mid)
        if end <= stemming_m + _EPS:
            tag = "collar"
        elif start >= length - bottom_length_m - _EPS:
            tag = "bottom"
        else:
            tag = "column"
        slices.append(
            HoleSlice(
                from_m=start,
                to_m=end,
                domain_id=domain_id,
                domain_name=domain_name,
                water=_covering_water(hole, mid),
                interval_tag=tag,
            )
        )
    return slices


def _in_range(value: float | None, minimum: float | None, maximum: float | None) -> bool:
    if minimum is None and maximum is None:
        return True
    if value is None:
        return False
    if minimum is not None and value < minimum - _EPS:
        return False
    if maximum is not None and value > maximum + _EPS:
        return False
    return True


def _water_matches(required: str, actual: str) -> bool:
    need = (required or "").strip().lower()
    have = (actual or "dry").strip().lower() or "dry"
    if not need or need in ("any", "*"):
        return True
    if need == "dry":
        return have == "dry"
    if need == "wet":
        return have in WET_WATER
    if need == "moist":
        return have == "moist"
    if need == "flowing":
        return have == "flowing"
    return have == need


def _interval_matches(required: str, tag: str, domain_id: str, domain_name: str) -> bool:
    need = (required or "").strip().lower()
    if not need or need in ("any", "*"):
        return True
    if need in ("bottom", "column", "collar"):
        return tag == need
    return need in {domain_id.lower(), domain_name.lower()}


def hole_level_matches(condition: ChargeCondition, hole: Hole, ctx: HoleChargeContext) -> bool:
    if condition.hole_kinds and hole.kind not in condition.hole_kinds:
        return False
    if condition.rows and hole.row not in condition.rows:
        return False
    if not _in_range(ctx.depth_m, condition.depth_min_m, condition.depth_max_m):
        return False
    if not _in_range(ctx.diameter_mm, condition.diameter_min_mm, condition.diameter_max_mm):
        return False
    if not _in_range(ctx.burden_m, condition.burden_min_m, condition.burden_max_m):
        return False
    if not _in_range(ctx.spacing_m, condition.spacing_min_m, condition.spacing_max_m):
        return False
    if not _in_range(ctx.distance_to_face_m, condition.distance_to_face_min_m, condition.distance_to_face_max_m):
        return False
    if not _in_range(ctx.target_pf, condition.target_pf_min, condition.target_pf_max):
        return False
    return True


def slice_matches(condition: ChargeCondition, sl: HoleSlice) -> bool:
    if condition.rock_domain_ids:
        allowed = {item.lower() for item in condition.rock_domain_ids}
        if sl.domain_id.lower() not in allowed and sl.domain_name.lower() not in allowed:
            return False
    if not _interval_matches(condition.geological_interval, sl.interval_tag, sl.domain_id, sl.domain_name):
        return False
    if not _water_matches(condition.water, sl.water):
        return False
    return True


def condition_matches(
    condition: ChargeCondition,
    hole: Hole,
    sl: HoleSlice,
    ctx: HoleChargeContext,
) -> bool:
    return hole_level_matches(condition, hole, ctx) and slice_matches(condition, sl)


def _subtract(span: tuple[float, float], occupied: Iterable[tuple[float, float]]) -> list[tuple[float, float]]:
    pieces = [span]
    for occ_from, occ_to in sorted(occupied):
        next_pieces: list[tuple[float, float]] = []
        for start, end in pieces:
            if occ_to <= start + _EPS or occ_from >= end - _EPS:
                next_pieces.append((start, end))
                continue
            if occ_from > start + _EPS:
                next_pieces.append((start, min(end, occ_from)))
            if occ_to < end - _EPS:
                next_pieces.append((max(start, occ_to), end))
        pieces = next_pieces
    return [(a, b) for a, b in pieces if b - a > _LENGTH_EPS]


def _occupied(claims: list[ClaimedSpan]) -> list[tuple[float, float]]:
    return [(c.from_m, c.to_m) for c in claims]


def _stemming_from_templates(
    hole: Hole,
    rules: dict[str, Any],
    templates: list[ChargeTemplate],
    ctx: HoleChargeContext,
) -> float:
    for template in sort_templates(templates):
        if not template.enabled or not hole_level_matches(template.conditions, hole, ctx):
            continue
        for action in template.actions:
            if action.kind != "stemming":
                continue
            if action.length_m is not None:
                return max(0.0, min(hole.length_m, action.length_m))
            return _stemming_from_rules(hole, rules)
    return _stemming_from_rules(hole, rules)


def _action_targets(
    action: ChargeAction,
    sl: HoleSlice,
    hole: Hole,
    stemming_m: float,
    bottom_length_m: float,
) -> list[tuple[float, float]]:
    """Where this action wants to write inside a matching slice."""
    length = hole.length_m
    chargeable = (stemming_m, length)
    if action.region == "collar":
        target = (0.0, stemming_m if stemming_m > 0 else min(action.length_m or 0.0, length))
    elif action.region == "bottom":
        bottom_len = action.length_m if action.length_m is not None else bottom_length_m
        target = (max(stemming_m, length - max(0.0, bottom_len)), length)
    elif action.region == "column":
        target = (stemming_m, max(stemming_m, length - bottom_length_m))
    elif action.region == "remaining":
        target = chargeable
    else:
        target = (sl.from_m, sl.to_m)
    start = max(target[0], sl.from_m)
    end = min(target[1], sl.to_m)
    if is_explosive_deck_kind(action.kind) or action.kind in {"air_deck", "inert_deck", "water_deck", "air"}:
        start = max(start, stemming_m)
    if end - start <= _LENGTH_EPS:
        return []
    return [(start, end)]


def apply_templates_to_hole(
    hole: Hole,
    rules: dict[str, Any],
    explosive: ExplosiveProperties,
    templates: list[ChargeTemplate],
    ctx: HoleChargeContext,
    catalog: dict[str, ExplosiveProperties],
) -> HoleLoad:
    stemming_m = _stemming_from_templates(hole, rules, templates, ctx)
    bottom_length_m = _bottom_length(rules, templates)
    slices = build_slices(hole, stemming_m, bottom_length_m)
    claims: list[ClaimedSpan] = []

    for template in sort_templates(templates):
        if not template.enabled:
            continue
        for action in template.actions:
            if action.kind == "stemming":
                continue
            for sl in slices:
                if not condition_matches(template.conditions, hole, sl, ctx):
                    continue
                for start, end in _action_targets(action, sl, hole, stemming_m, bottom_length_m):
                    for free_from, free_to in _subtract((start, end), _occupied(claims)):
                        claims.append(
                            ClaimedSpan(
                                from_m=free_from,
                                to_m=free_to,
                                action=action,
                                template_id=template.id,
                            )
                        )

    leftover_action = ChargeAction(
        kind="bulk_explosive",
        explosive_key=explosive.name,
        region="remaining",
        place_primer=True,
    )
    for sl in slices:
        if sl.interval_tag == "collar":
            continue
        start = max(sl.from_m, stemming_m)
        end = sl.to_m
        for free_from, free_to in _subtract((start, end), _occupied(claims)):
            claims.append(
                ClaimedSpan(
                    from_m=free_from,
                    to_m=free_to,
                    action=leftover_action,
                    template_id="",
                )
            )

    decks = _claims_to_decks(hole, rules, explosive, catalog, stemming_m, claims)
    primers, primer_items = _primers_from_claims(rules, explosive, claims, leftover_action)
    if stemming_m > _EPS:
        decks.append(Deck(kind="stemming", from_m=0.0, to_m=stemming_m))
    decks.sort(key=lambda d: (d.from_m, d.to_m))

    total_charge_kg = sum(d.mass_kg for d in decks if is_explosive_deck_kind(d.kind))
    grid_a_m = float(rules.get("grid_a_m", 0.0) or 0.0)
    grid_b_m = float(rules.get("grid_b_m", 0.0) or 0.0)
    influence_volume_m3 = grid_a_m * grid_b_m * hole.bench_height_m
    specific_q = total_charge_kg / influence_volume_m3 if influence_volume_m3 > 0 else 0.0

    return HoleLoad(
        hole_id=hole.id,
        decks=decks,
        total_charge_kg=total_charge_kg,
        influence_volume_m3=influence_volume_m3,
        specific_q_kg_m3=specific_q,
        primers=primers,
        primer_items=primer_items,
    )


def _lookup_explosive(
    key: str,
    catalog: dict[str, ExplosiveProperties],
    default: ExplosiveProperties,
) -> ExplosiveProperties:
    if key and key in catalog:
        return catalog[key]
    lowered = {name.lower(): item for name, item in catalog.items()}
    if key and key.lower() in lowered:
        return lowered[key.lower()]
    return default


def _deck_mass(
    hole: Hole,
    rules: dict[str, Any],
    action: ChargeAction,
    from_m: float,
    to_m: float,
    catalog: dict[str, ExplosiveProperties],
    default: ExplosiveProperties,
) -> float:
    if not is_explosive_deck_kind(action.kind):
        return 0.0
    if action.mass_kg is not None:
        return max(0.0, action.mass_kg)
    chosen = _lookup_explosive(action.explosive_key or action.product, catalog, default)
    diameter = charge_diameter_m(hole.diameter_mm, float(rules.get("hole_oversize_coeff", 1.05)))
    capacity = linear_capacity_kg_per_m(diameter, chosen.density_t_m3)
    return (to_m - from_m) * capacity


def _merge_decks(decks: list[Deck]) -> list[Deck]:
    if not decks:
        return []
    ordered = sorted(decks, key=lambda d: (d.from_m, d.to_m))
    merged = [ordered[0]]
    for deck in ordered[1:]:
        prev = merged[-1]
        same = (
            prev.kind == deck.kind
            and prev.explosive_key == deck.explosive_key
            and prev.product == deck.product
            and abs(prev.to_m - deck.from_m) <= _LENGTH_EPS
        )
        if same:
            merged[-1] = replace(
                prev,
                to_m=deck.to_m,
                mass_kg=prev.mass_kg + deck.mass_kg,
            )
        else:
            merged.append(deck)
    return merged


def _claims_to_decks(
    hole: Hole,
    rules: dict[str, Any],
    explosive: ExplosiveProperties,
    catalog: dict[str, ExplosiveProperties],
    stemming_m: float,
    claims: list[ClaimedSpan],
) -> list[Deck]:
    decks: list[Deck] = []
    for claim in claims:
        if claim.to_m - claim.from_m <= _LENGTH_EPS:
            continue
        kind = claim.action.kind
        if kind == "charge":
            kind = "bulk_explosive"
        if kind == "air":
            kind = "air_deck"
        product = claim.action.product or claim.action.explosive_key
        mass = _deck_mass(hole, rules, claim.action, claim.from_m, claim.to_m, catalog, explosive)
        decks.append(
            Deck(
                kind=kind,
                from_m=claim.from_m,
                to_m=claim.to_m,
                explosive_key=claim.action.explosive_key or claim.action.product,
                mass_kg=mass,
                product=product,
            )
        )
    return _merge_decks(decks)


def _primers_from_claims(
    rules: dict[str, Any],
    explosive: ExplosiveProperties,
    claims: list[ClaimedSpan],
    leftover_action: ChargeAction,
) -> tuple[list[float], list[Primer]]:
    default_offset = max(0.0, float(rules.get("primer_offset_m", 0.3) or 0.3))
    items: list[Primer] = []
    seen: set[float] = set()
    for claim in sorted(claims, key=lambda c: c.from_m):
        action = claim.action
        if not is_explosive_deck_kind(action.kind):
            continue
        if not action.place_primer and action is not leftover_action:
            continue
        offset = action.primer_offset_m if action.primer_offset_m is not None else default_offset
        position = max(claim.from_m, claim.to_m - offset)
        rounded = round(position, 6)
        if rounded in seen:
            continue
        seen.add(rounded)
        items.append(
            Primer(
                position_m=position,
                product=action.primer_product or action.explosive_key or explosive.name,
                mass_kg=action.primer_mass_kg,
                kind=action.primer_kind,
            )
        )
    return [item.position_m for item in items], items


def apply_charge_templates(
    holes: list[Hole],
    rules: dict[str, Any],
    explosive: ExplosiveProperties,
    *,
    contour: BlockContour | None = None,
    catalog: dict[str, ExplosiveProperties] | None = None,
    templates: list[ChargeTemplate] | None = None,
) -> list[HoleLoad]:
    resolved = templates if templates is not None else templates_from_rules(rules)
    products = dict(catalog or {})
    products.setdefault(explosive.name, explosive)
    loads: list[HoleLoad] = []
    for hole in holes:
        ctx = build_hole_context(hole, holes, rules, contour, explosive)
        loads.append(
            apply_templates_to_hole(hole, rules, explosive, resolved, ctx, products)
        )
    return loads
