"""The geometry the emblem motifs are drawn from.

The site's visual language is a compass bezel: a ring of graduated ticks, a
needle, an arc of lettering. Trigonometry does not belong in a template, so the
coordinates are computed here and the templates only draw what they are given.

Nothing here knows about colours or sizes in pixels — every figure is in the
same 0..100 user space, and the SVG viewBox is what turns it into a size.
"""

from __future__ import annotations

import math
from typing import Any

#: The centre of every figure, in user space.
CENTRE = 50.0


def bezel_ticks(
    count: int = 72,
    outer: float = 49.0,
    minor: float = 45.0,
    major: float = 41.5,
    major_every: int = 6,
    start_deg: float = 0.0,
    sweep_deg: float = 360.0,
) -> list[dict[str, Any]]:
    """The graduated ring: ``count`` ticks, every ``major_every``-th one long.

    Angles run clockwise from twelve o'clock, which is how a compass card is
    read and, more practically, means tick 0 is always at the top of the figure
    whatever the sweep.

    Args:
        count: How many ticks around the ring.
        outer: Radius the ticks start at.
        minor: Radius a short tick reaches.
        major: Radius a long tick reaches.
        major_every: One tick in this many is drawn long.
        start_deg: Where the first tick sits, in degrees from twelve o'clock.
        sweep_deg: How far round the ring the ticks run.

    Returns:
        One dict per tick with x1/y1/x2/y2 and whether it is a major tick.
    """
    if count < 1:
        return []

    # A full ring closes on itself, so the last tick would land on the first;
    # an open sweep (an arc) wants a tick at both ends.
    closed = abs(sweep_deg % 360.0) < 1e-9
    divisor = count if closed else max(count - 1, 1)

    ticks: list[dict[str, Any]] = []
    for index in range(count):
        angle = math.radians(start_deg + sweep_deg * index / divisor - 90.0)
        is_major = index % major_every == 0
        inner = major if is_major else minor
        ticks.append({
            "x1": round(CENTRE + outer * math.cos(angle), 3),
            "y1": round(CENTRE + outer * math.sin(angle), 3),
            "x2": round(CENTRE + inner * math.cos(angle), 3),
            "y2": round(CENTRE + inner * math.sin(angle), 3),
            "major": is_major,
        })
    return ticks


def arc_path(radius: float, start_deg: float = -110.0, end_deg: float = 110.0) -> str:
    """An SVG path along which text is set, clockwise from ``start_deg``.

    Used for the lettering that curves over the medallion. Degrees are measured
    from twelve o'clock like everything else here.
    """
    start = math.radians(start_deg - 90.0)
    end = math.radians(end_deg - 90.0)
    x1 = round(CENTRE + radius * math.cos(start), 3)
    y1 = round(CENTRE + radius * math.sin(start), 3)
    x2 = round(CENTRE + radius * math.cos(end), 3)
    y2 = round(CENTRE + radius * math.sin(end), 3)
    large = 1 if (end_deg - start_deg) % 360 > 180 else 0
    return f"M {x1} {y1} A {radius} {radius} 0 {large} 1 {x2} {y2}"


def gauge(values: list[float], span_deg: float = 148.0) -> list[dict[str, Any]]:
    """Where each marker sits on the open arc the figures are read off.

    ``values`` are 0..1 along the arc. The arc is centred on twelve o'clock and
    opens ``span_deg`` wide, so 0.5 is straight up.
    """
    markers: list[dict[str, Any]] = []
    for value in values:
        clamped = min(max(value, 0.0), 1.0)
        degrees = -span_deg / 2 + span_deg * clamped
        angle = math.radians(degrees - 90.0)
        markers.append({
            "deg": round(degrees, 3),
            "x": round(CENTRE + 44.0 * math.cos(angle), 3),
            "y": round(CENTRE + 44.0 * math.sin(angle), 3),
            "label_x": round(CENTRE + 33.0 * math.cos(angle), 3),
            "label_y": round(CENTRE + 33.0 * math.sin(angle), 3),
        })
    return markers
