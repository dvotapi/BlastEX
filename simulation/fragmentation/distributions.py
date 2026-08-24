"""Size-distribution helpers shared by Kuznetsov, Kuz-Ram and Swebrec."""
from __future__ import annotations

import math
from collections.abc import Callable

from simulation.fragmentation.models import DistributionPoint

# Default uniformity for the Kuznetsov-only model (Cunningham n is Kuz-Ram).
DEFAULT_KUZNETSOV_N = 1.0

# Typical Swebrec undulation; Ouchterlony often reports b around 2–2.5.
DEFAULT_SWEBREC_B = 2.27

SIEVE_MM = (
    1.0,
    2.0,
    4.0,
    8.0,
    16.0,
    25.0,
    40.0,
    50.0,
    70.0,
    100.0,
    150.0,
    200.0,
    300.0,
    400.0,
    500.0,
    700.0,
    1000.0,
    1500.0,
)


def rosin_rammler_characteristic_mm(x50_mm: float, n: float) -> float:
    """xc such that x50 = xc * (ln 2)^(1/n)."""
    if x50_mm <= 0 or n <= 0:
        raise ValueError("x50 and Rosin–Rammler n must be positive.")
    return x50_mm / math.pow(math.log(2.0), 1.0 / n)


def rosin_rammler_size_mm(passing: float, x50_mm: float, n: float) -> float:
    """Size at a passing fraction in (0, 1) for the Rosin–Rammler curve."""
    if passing <= 0.0:
        return 0.0
    if passing >= 1.0:
        return float("inf")
    xc = rosin_rammler_characteristic_mm(x50_mm, n)
    return xc * math.pow(-math.log(1.0 - passing), 1.0 / n)


def rosin_rammler_passing(size_mm: float, x50_mm: float, n: float) -> float:
    """Passing fraction P(X < size) for Rosin–Rammler."""
    if size_mm <= 0.0:
        return 0.0
    xc = rosin_rammler_characteristic_mm(x50_mm, n)
    return 1.0 - math.exp(-math.pow(size_mm / xc, n))


def rosin_rammler_oversize_pct(x50_mm: float, n: float, lump_size_mm: float) -> float:
    """Percent retained above the lump size. Matches ``Blast.py``."""
    if lump_size_mm <= 0.0:
        return 100.0
    xc = rosin_rammler_characteristic_mm(x50_mm, n)
    return math.exp(-math.pow(lump_size_mm / xc, n)) * 100.0


def swebrec_passing(size_mm: float, x50_mm: float, xmax_mm: float, b: float) -> float:
    """Swebrec passing fraction P(x) for 0 < x ≤ xmax."""
    if size_mm <= 0.0:
        return 0.0
    if xmax_mm <= 0.0 or x50_mm <= 0.0 or b <= 0.0:
        raise ValueError("Swebrec x50, xmax and b must be positive.")
    if size_mm >= xmax_mm:
        return 1.0
    if x50_mm >= xmax_mm:
        return 1.0 if size_mm >= x50_mm else 0.0
    ratio = math.log(xmax_mm / size_mm) / math.log(xmax_mm / x50_mm)
    return 1.0 / (1.0 + math.pow(ratio, b))


def swebrec_size_mm(passing: float, x50_mm: float, xmax_mm: float, b: float) -> float:
    """Invert Swebrec: size at a passing fraction in (0, 1)."""
    if passing <= 0.0:
        return 0.0
    if passing >= 1.0:
        return xmax_mm
    if xmax_mm <= x50_mm or b <= 0.0 or x50_mm <= 0.0:
        raise ValueError("Swebrec inversion requires 0 < x50 < xmax and b > 0.")
    exponent = math.pow((1.0 - passing) / passing, 1.0 / b)
    return xmax_mm / math.pow(xmax_mm / x50_mm, exponent)


def swebrec_oversize_pct(lump_size_mm: float, x50_mm: float, xmax_mm: float, b: float) -> float:
    return (1.0 - swebrec_passing(lump_size_mm, x50_mm, xmax_mm, b)) * 100.0


def distribution_curve(
    passing_fn: Callable[[float], float],
    extra_sizes_mm: tuple[float, ...] = (),
) -> list[DistributionPoint]:
    """Passing curve at standard sieves plus any extra characteristic sizes."""
    sizes = {float(size) for size in SIEVE_MM if size > 0}
    sizes.update(float(size) for size in extra_sizes_mm if size and size > 0)
    points = [
        DistributionPoint(size_mm=round(size, 3), passing_pct=round(passing_fn(size) * 100.0, 3))
        for size in sorted(sizes)
    ]
    return points
