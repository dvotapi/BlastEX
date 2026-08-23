"""Engineering simulations that sit beside spatial blast design.

Fragmentation (BDX-006) lives here so ``Blast.py`` stays an optimisation
facade and does not own the size-distribution models.
"""

from simulation.fragmentation import FRAGMENTATION_MODELS

__all__ = ["FRAGMENTATION_MODELS"]
