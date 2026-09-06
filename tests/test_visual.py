"""The committed visual baseline: every scene, at every width.

These are the tests that notice a stylesheet change nobody meant to make. What
each one asserts is narrow — this page, at this width, still looks like the
committed picture — and between them they cover the whole site, which is the
only kind of coverage a layout has.

Marked slow: they drive a real browser. ``make screenshots`` rewrites the
baseline after an intended change; look at the diff before committing it.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

import visual
from pages import VIEWPORTS

pytestmark = pytest.mark.slow

#: The states worth a picture. A scene is a path plus whatever has to be done
#: to the page once it is open.
SCENES: dict[str, str] = {
    "home": "/",
    "notfound": "/no-existe",
}

#: Full-page shots are the point on the long page and pure weight on the short
#: ones, where the whole thing fits in the viewport anyway.
FULL_PAGE = {"home"}

#: Three widths rather than five for the baseline: a phone, a tablet and a
#: desktop are where this layout actually changes shape, and every committed
#: picture is a megabyte somebody has to review.
BASELINE_VIEWPORTS = [
    view for view in VIEWPORTS
    if view[0] in {"mobile-375", "tablet-768", "desktop-1280"}
]


@pytest.fixture()
def shot_page(browser_instance: Any, live_server: str, db_clean: None) -> Iterator[Any]:
    """A page factory: open a path at a width, ready to be photographed."""
    pages: list[Any] = []
    contexts: list[Any] = []

    def open_at(path: str, width: int, height: int) -> Any:
        context = browser_instance.new_context(
            viewport={"width": width, "height": height},
            device_scale_factor=1,
            reduced_motion="no-preference",
        )
        contexts.append(context)
        page = context.new_page()
        pages.append(page)
        visual.block_web_fonts(page)
        page.goto(f"{live_server}{path}", wait_until="networkidle")
        return page

    try:
        yield open_at
    finally:
        for page in pages:
            page.close()
        for context in contexts:
            context.close()


@pytest.mark.parametrize("scene", sorted(SCENES))
@pytest.mark.parametrize("name,width,height", BASELINE_VIEWPORTS)
def test_scene_matches_the_baseline(
    shot_page: Any, browser_instance: Any, scene: str, name: str,
    width: int, height: int,
) -> None:
    page = shot_page(SCENES[scene], width, height)
    visual.compare(page, browser_instance, f"{scene}-{name}",
                   full_page=scene in FULL_PAGE)


@pytest.mark.parametrize("name,width,height", BASELINE_VIEWPORTS)
def test_the_open_index_matches_the_baseline(
    shot_page: Any, browser_instance: Any, name: str, width: int, height: int,
) -> None:
    # The index is the whole navigation, and it is the one screen that exists
    # only as a state — no URL of its own, so nothing else would photograph it.
    page = shot_page("/", width, height)
    page.click("#menuOpen")
    page.wait_for_selector("#menu.open")
    visual.compare(page, browser_instance, f"menu-{name}", full_page=False)


def test_the_baseline_is_not_empty() -> None:
    """A deleted baseline directory has to fail, not quietly pass.

    Every test above skips when its own renderer has no committed set — which
    is the right answer for a machine nobody has photographed yet, and the
    wrong one for a repository that lost its screenshots. This is the guard
    against the second case.
    """
    sets = [directory for directory in visual.BASELINE_ROOT.glob("*")
            if directory.is_dir() and list(directory.glob("*.png"))]
    assert sets, (
        "tests/screenshots/ holds no committed baseline at all — "
        "run: make screenshots"
    )
