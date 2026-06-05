"""Tests for dice rolling."""

from landgrab.core.dice import roll


def test_roll_range():
    results = {roll(8) for _ in range(200)}
    assert results.issubset(set(range(1, 9)))
    assert len(results) > 1  # should see multiple values


def test_roll_custom_sides():
    results = {roll(6) for _ in range(100)}
    assert results.issubset(set(range(1, 7)))
