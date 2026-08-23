"""Profile weights over PREDICTED Pareto objectives.

BALANCED reuses the BDX-017 utopia compromise. Other profiles apply
explicit dimensionless weights. No scalar RL reward and no unit conversion.
"""
from __future__ import annotations

from design.optimization.pareto import objective_vector, pick_compromise
from design.optimization.types import OptimizationCandidate
from design.recommendation.types import (
    PROFILE_BALANCED,
    PROFILE_KEYS,
    PROFILES,
    RecommendationProfile,
)


class UnknownProfileError(ValueError):
    """Raised when the requested recommendation profile is not defined."""


def profile_spec(key: str) -> RecommendationProfile:
    token = (key or "").strip().upper().replace(" ", "_").replace("-", "_")
    aliases = {
        "LOWCOST": "LOW_COST",
        "FINE": "FINE_FRAGMENTATION",
        "FRAGMENTATION": "FINE_FRAGMENTATION",
        "VIBRATION": "LOW_VIBRATION",
        "PPV": "LOW_VIBRATION",
    }
    token = aliases.get(token, token)
    spec = PROFILES.get(token)
    if spec is None:
        known = ", ".join(PROFILE_KEYS)
        raise UnknownProfileError(f"Неизвестный профиль рекомендации «{key}». Допустимы: {known}.")
    return spec


def _ranges(
    candidates: list[OptimizationCandidate],
    keys: list[str],
) -> tuple[list[float], list[float]] | None:
    vectors: list[list[float]] = []
    for item in candidates:
        vector = objective_vector(item, keys)
        if vector is not None:
            vectors.append(vector)
    if not vectors:
        return None
    mins = [min(row[index] for row in vectors) for index in range(len(keys))]
    maxs = [max(row[index] for row in vectors) for index in range(len(keys))]
    return mins, maxs


def weighted_distance(
    candidate: OptimizationCandidate,
    keys: list[str],
    weights: dict[str, float],
    mins: list[float],
    maxs: list[float],
) -> float | None:
    vector = objective_vector(candidate, keys)
    if vector is None:
        return None
    total = 0.0
    for key, value, low, high in zip(keys, vector, mins, maxs):
        span = high - low
        # Declared unit stays as-is; normalisation is dimensionless.
        norm = 0.0 if span <= 0 else (value - low) / span
        weight = float(weights.get(key) or 0.0)
        if weight < 0:
            weight = 0.0
        total += weight * norm * norm
    return total


def candidate_pool(candidates: list[OptimizationCandidate]) -> list[OptimizationCandidate]:
    """Prefer the first Pareto front; fall back to any feasible overlay."""
    front = [item for item in candidates if item.on_pareto and item.feasible]
    if front:
        return front
    feasible = [item for item in candidates if item.feasible]
    return feasible or list(candidates)


def pick_for_profile(
    candidates: list[OptimizationCandidate],
    profile_key: str,
    objective_keys: list[str],
) -> OptimizationCandidate | None:
    spec = profile_spec(profile_key)
    pool = candidate_pool(candidates)
    if not pool:
        return None
    if spec.key == PROFILE_BALANCED:
        return pick_compromise(pool, objective_keys)
    primary = [key for key in spec.primary_objectives if key in objective_keys] or list(objective_keys)
    primary_ranges = _ranges(pool, primary)
    full_ranges = _ranges(pool, objective_keys)
    if primary_ranges is None:
        return None
    primary_mins, primary_maxs = primary_ranges
    full_mins, full_maxs = full_ranges if full_ranges is not None else primary_ranges
    ranked: list[tuple[float, float, str, OptimizationCandidate]] = []
    for item in pool:
        primary_distance = weighted_distance(item, primary, spec.weights, primary_mins, primary_maxs)
        if primary_distance is None:
            continue
        full_distance = weighted_distance(item, objective_keys, spec.weights, full_mins, full_maxs)
        ranked.append((primary_distance, full_distance if full_distance is not None else primary_distance, item.candidate_id, item))
    if not ranked:
        return None
    ranked.sort(key=lambda row: (row[0], row[1], row[2]))
    return ranked[0][3]


def profile_winners(
    candidates: list[OptimizationCandidate],
    objective_keys: list[str],
) -> dict[str, OptimizationCandidate]:
    winners: dict[str, OptimizationCandidate] = {}
    for key in PROFILE_KEYS:
        picked = pick_for_profile(candidates, key, objective_keys)
        if picked is not None:
            winners[key] = picked
    return winners
