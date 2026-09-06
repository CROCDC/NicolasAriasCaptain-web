"""The geometry the emblem motifs are drawn from.

Trigonometry in a template is unreadable and untestable, so it lives in a
service — and a bezel whose ticks drift off the ring is a thing worth failing a
build over, because by eye it only ever looks "a bit off".
"""

from __future__ import annotations

import math
import re

import pytest

from app.services import emblem

#: Coordinates are rounded to three decimals for the SVG, so a radius comes
#: back a hair off. Anything larger than this is a tick that missed the ring.
ROUNDING = 0.002


def _radius(x: float, y: float) -> float:
    return math.hypot(x - emblem.CENTRE, y - emblem.CENTRE)


def test_a_closed_ring_has_one_tick_per_division() -> None:
    ticks = emblem.bezel_ticks(72)
    assert len(ticks) == 72
    # A full ring closes on itself: the last tick must not land on the first.
    assert (ticks[0]["x1"], ticks[0]["y1"]) != (ticks[-1]["x1"], ticks[-1]["y1"])


def test_every_tick_starts_on_the_ring_and_points_inwards() -> None:
    for tick in emblem.bezel_ticks(72, outer=47.0, minor=43.0, major=40.0):
        assert _radius(tick["x1"], tick["y1"]) == pytest.approx(47.0, abs=ROUNDING)
        inner = _radius(tick["x2"], tick["y2"])
        assert inner == pytest.approx(40.0 if tick["major"] else 43.0, abs=ROUNDING)
        assert inner < 47.0


def test_the_first_tick_is_at_twelve_oclock_and_is_major() -> None:
    first = emblem.bezel_ticks(72)[0]
    assert first["major"] is True
    assert first["x1"] == emblem.CENTRE
    assert first["y1"] < emblem.CENTRE


def test_one_tick_in_six_is_major_by_default() -> None:
    ticks = emblem.bezel_ticks(72)
    assert sum(1 for tick in ticks if tick["major"]) == 12


def test_an_open_arc_carries_a_tick_at_both_ends() -> None:
    ticks = emblem.bezel_ticks(25, start_deg=-74, sweep_deg=148)
    assert len(ticks) == 25
    # Symmetric about twelve o'clock: the two ends mirror each other.
    assert ticks[0]["x1"] == pytest.approx(100 - ticks[-1]["x1"], abs=ROUNDING)
    assert ticks[0]["y1"] == pytest.approx(ticks[-1]["y1"], abs=ROUNDING)


def test_no_ticks_is_no_ticks_rather_than_a_crash() -> None:
    assert emblem.bezel_ticks(0) == []


def test_the_arc_path_is_a_single_svg_arc_at_the_asked_radius() -> None:
    path = emblem.arc_path(44)
    assert re.match(r"^M [-\d.]+ [-\d.]+ A 44 44 0 [01] 1 [-\d.]+ [-\d.]+$", path)

    numbers = [float(value) for value in re.findall(r"[-\d.]+", path)]
    assert _radius(numbers[0], numbers[1]) == pytest.approx(44.0, abs=ROUNDING)


def test_the_gauge_reads_left_to_right_with_the_middle_straight_up() -> None:
    left, middle, right = emblem.gauge([0.0, 0.5, 1.0])
    assert left["x"] < middle["x"] < right["x"]
    assert middle["x"] == emblem.CENTRE
    assert middle["y"] < emblem.CENTRE


def test_a_value_off_the_scale_is_clamped_onto_it() -> None:
    assert emblem.gauge([-3.0])[0] == emblem.gauge([0.0])[0]
    assert emblem.gauge([9.0])[0] == emblem.gauge([1.0])[0]
