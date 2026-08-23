"""Non-dominated sorting. All objectives are minimized. No scalar RL reward."""
from __future__ import annotations

from design.optimization.types import OptimizationCandidate


def dominates(left: list[float], right: list[float]) -> bool:
    """True if left is at least as good in every coordinate and better in one."""
    if len(left) != len(right) or not left:
        return False
    not_worse = all(a <= b for a, b in zip(left, right))
    better = any(a < b for a, b in zip(left, right))
    return not_worse and better


def objective_vector(candidate: OptimizationCandidate, keys: list[str]) -> list[float] | None:
    values: list[float] = []
    for key in keys:
        raw = candidate.objectives.get(key)
        if raw is None:
            return None
        values.append(float(raw))
    return values


def mark_pareto(candidates: list[OptimizationCandidate], keys: list[str]) -> list[OptimizationCandidate]:
    """Set on_pareto / pareto_rank. Rank 1 is the first front."""
    scored: list[tuple[OptimizationCandidate, list[float]]] = []
    for item in candidates:
        vector = objective_vector(item, keys) if item.feasible else None
        if vector is None:
            item.on_pareto = False
            item.pareto_rank = 0
            continue
        scored.append((item, vector))

    remaining = list(scored)
    rank = 1
    while remaining:
        front = [
            item
            for item, vector in remaining
            if not any(dominates(other, vector) for other_item, other in remaining if other_item is not item)
        ]
        front_ids = {item.candidate_id for item in front}
        for item in front:
            item.pareto_rank = rank
            item.on_pareto = rank == 1
        remaining = [pair for pair in remaining if pair[0].candidate_id not in front_ids]
        rank += 1

    return [item for item in candidates if item.on_pareto]


def pick_compromise(front: list[OptimizationCandidate], keys: list[str]) -> OptimizationCandidate | None:
    """Utopia-distance pick on the first front. Deterministic tie-break by id."""
    scored: list[tuple[OptimizationCandidate, list[float]]] = []
    for item in front:
        vector = objective_vector(item, keys)
        if vector is not None:
            scored.append((item, vector))
    if not scored:
        return None
    mins = [min(row[index] for _, row in scored) for index in range(len(keys))]
    maxs = [max(row[index] for _, row in scored) for index in range(len(keys))]

    def distance(pair: tuple[OptimizationCandidate, list[float]]) -> tuple[float, str]:
        item, vector = pair
        total = 0.0
        for value, low, high in zip(vector, mins, maxs):
            span = high - low
            norm = 0.0 if span <= 0 else (value - low) / span
            total += norm * norm
        return (total, item.candidate_id)

    scored.sort(key=distance)
    return scored[0][0]
