"""Engineering simulations that sit beside spatial blast design.

Fragmentation (BDX-006) lives here so ``Blast.py`` stays an optimisation
facade and does not own the size-distribution models.

Movement / heave (BDX-023) is an empirical kinematic *estimate*, not a
validated physics engine. It writes only the PREDICTED overlay.
"""

from simulation.fragmentation import FRAGMENTATION_MODELS
from simulation.movement import MODEL_ID as MOVEMENT_MODEL_ID

__all__ = ["FRAGMENTATION_MODELS", "MOVEMENT_MODEL_ID"]
