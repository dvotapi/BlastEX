"""Combined execution comparisons (phase BDX-009).

Design vs drilled / charged / fired. Designed Hole, HoleLoad and network
are never overwritten.
"""
from __future__ import annotations

from typing import Any

from design.as_charged import compare_design as compare_charged
from design.as_drilled import compare_design as compare_drilled
from design.as_fired import compare_design as compare_fired
from design.models import BlastDesign


def compare_execution(design: BlastDesign) -> dict[str, Any]:
    """Three independent reports. Each report re-reads designed data only."""
    holes_before = [hole.to_dict() for hole in design.holes]
    loads_before = [load.to_dict() for load in design.loads]
    network_before = (
        [item.to_dict() for item in design.network.detonators],
        dict(design.network.electronic_times_ms),
        [item.to_dict() for item in design.network.firing_events],
    )
    drilled = compare_drilled(design)
    charged = compare_charged(design)
    fired = compare_fired(design)
    if [hole.to_dict() for hole in design.holes] != holes_before:
        raise RuntimeError("Сводка исполнения не должна менять проектные скважины.")
    if [load.to_dict() for load in design.loads] != loads_before:
        raise RuntimeError("Сводка исполнения не должна менять проектный заряд.")
    network_after = (
        [item.to_dict() for item in design.network.detonators],
        dict(design.network.electronic_times_ms),
        [item.to_dict() for item in design.network.firing_events],
    )
    if network_after != network_before:
        raise RuntimeError("Сводка исполнения не должна менять проектную сеть.")
    designed_count = len([hole for hole in design.holes if hole.enabled])
    return {
        "role": "executed",
        "designed_count": designed_count,
        "design_vs_drilled": drilled,
        "design_vs_charged": charged,
        "design_vs_fired": fired,
        "as_drilled_count": len(design.as_drilled_holes),
        "as_charged_count": len(design.as_charged_holes),
        "as_fired_count": len(design.as_fired_holes),
        "warnings": list(drilled.get("warnings", []))
        + list(charged.get("warnings", []))
        + list(fired.get("warnings", [])),
    }
