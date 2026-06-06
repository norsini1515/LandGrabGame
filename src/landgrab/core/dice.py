"""Dice rolling utilities."""

import random


def roll(sides: int | None = None, rng: random.Random | None = None) -> int:
    """Roll a single die; sides defaults to die value from terrain.config."""
    if sides is None:
        from landgrab.core import config
        sides = config.die_sides()
    r = rng or random
    return r.randint(1, sides)
