"""Dice rolling utilities."""

import random


def roll(sides: int = 8, rng: random.Random | None = None) -> int:
    """Roll a single die with the given number of sides (default d8)."""
    r = rng or random
    return r.randint(1, sides)
