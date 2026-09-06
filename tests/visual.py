"""Visual regression: compare a screenshot against the committed baseline.

A screenshot suite that only produces images is a suite that catches a change
when somebody happens to look. This makes a visual change fail the build.

Four things make that workable rather than maddening:

* **A baseline per renderer.** The same page is not the same pixels in two
  browsers or on two operating systems, so the baselines live under
  ``screenshots/<platform>-<browser>/``. A renderer with no committed set skips
  loudly and says how to create one, rather than comparing against somebody
  else's pixels.
* **No shot depends on a third party.** Cinzel, Fraunces and Karla used to come
  from Google, and a baseline that changed with the network was worse than
  none, so the request was refused and the pages rendered in fallback stacks.
  The typefaces are served from ``/static/fonts`` now, so they load every time
  and the baseline finally shows the site's real lettering — deterministic
  *and* true, where before it could only be one of the two. The Google hosts
  stay blocked so a stray reference cannot quietly reintroduce the dependency.
* **Everything that moves is stopped.** Reveal-on-scroll, transitions and the
  caret are frozen before the shot, so two runs of the same code agree.
* **A tolerance.** Font rasterisation is not bit-identical run to run, so a
  handful of differing pixels is noise. A real layout change moves thousands.

Set ``UPDATE_SCREENSHOTS=1`` to rewrite the baseline after an intended change —
that is what ``make screenshots`` does. Look at the diff before committing it:
that is the whole point of a baseline.
"""

from __future__ import annotations

import io
import os
import pathlib
import sys
from typing import Any

from PIL import Image, ImageChops, ImageStat

#: Where the committed sets live, one directory per renderer.
BASELINE_ROOT = pathlib.Path(__file__).parent / "screenshots"

#: A pixel counts as changed above this per-channel difference.
CHANNEL_TOLERANCE = 24

#: And the shot fails above this share of changed pixels.
MAX_CHANGED = 0.002

#: Regions whose content is expected to differ: the footer year, which the
#: page writes from the visitor's own clock and which would turn every
#: baseline red on the first of January. Masked at the element's own box, so a
#: layout change still moves the patch and still fails.
DYNAMIC = ["#currentYear"]

#: Hosts the shots must not depend on. See the module docstring. The shared
#: Next Tech footer is one of them: it is a remote Web Component that adds 62px
#: to the page when it renders, so an unreachable nexttech.com.ar would fail the
#: size assertion rather than the layout. Blocking it reproduces exactly what
#: that outage looks like in production — the footer does not render, nothing
#: else moves — and leaves how it *looks* to a human, same as the web fonts.
BLOCKED = [
    "**://fonts.googleapis.com/**",
    "**://fonts.gstatic.com/**",
    "**://nexttech.com.ar/**",
]

_STILL = """
*, *::before, *::after {
  animation: none !important;
  transition: none !important;
  animation-duration: 0s !important;
  transition-duration: 0s !important;
  caret-color: transparent !important;
  scroll-behavior: auto !important;
}
.reveal { opacity: 1 !important; transform: none !important; }
"""


def texture(shot_bytes: bytes) -> float:
    """How much a shot varies pixel to pixel.

    A photograph is textured; a box that failed to paint is one flat colour.
    Used to assert against the page itself, where a baseline can only ever
    compare a picture to an older picture of the same mistake.
    """
    image = Image.open(io.BytesIO(shot_bytes)).convert("L")
    return ImageStat.Stat(image).stddev[0]


def renderer_name(browser: Any) -> str:
    """Which committed set this run compares against.

    Overridable so a run can be pointed at another renderer's baseline, which
    is how a set is regenerated for a machine you are not sitting at.
    """
    override = os.environ.get("SCREENSHOT_RENDERER")
    if override:
        return override
    return f"{sys.platform}-{browser.browser_type.name}"


def baseline_dir(browser: Any) -> pathlib.Path:
    return BASELINE_ROOT / renderer_name(browser)


def block_web_fonts(page: Any) -> None:
    """Refuse the font requests, so the shot does not depend on the network."""
    for pattern in BLOCKED:
        page.route(pattern, lambda route: route.abort())


def settle(page: Any) -> None:
    """Stop everything that moves, and let every photograph finish arriving.

    The stylesheet handles animation and transition; the reveal is also forced
    on directly, because an element the observer has not reached yet is
    transparent by class rather than by transition.

    Getting the photographs into the shot takes three separate things, and
    missing any one of them yields a baseline full of empty boxes — which then
    passes forever, because it is compared against itself:

    * The rail scrolls sideways, so its images never enter the viewport and a
      lazy one is never fetched. Every image is made eager instead.
    * ``complete`` has to be awaited, or the shot races the download.
    * The tags carry ``decoding="async"``, so a loaded image is still not a
      painted one; a full-page capture renders nothing for it until it has
      been decoded. ``decode()`` is what actually puts the photograph on the
      page, and it is the step whose absence is hardest to notice.
    """
    page.add_style_tag(content=_STILL)
    page.evaluate("""() => {
      document.querySelectorAll('.reveal').forEach(el => el.classList.add('visible'));
      document.querySelectorAll('img[loading="lazy"]').forEach(img => {
        img.loading = 'eager';
      });
      window.scrollTo(0, document.body.scrollHeight);
    }""")
    page.wait_for_function(
        "() => Array.from(document.images).every(img => img.complete)",
        timeout=15000)
    page.evaluate(
        "() => Promise.all(Array.from(document.images)"
        ".map(img => img.decode().catch(() => {})))")
    page.evaluate("() => window.scrollTo(0, 0)")
    page.wait_for_timeout(250)


def _mask_locators(page: Any) -> list[Any]:
    """The dynamic regions actually present on this page."""
    masks = []
    for selector in DYNAMIC:
        locator = page.locator(selector)
        if locator.count():
            masks.append(locator)
    return masks


def _changed_share(baseline: Image.Image, shot: Image.Image) -> tuple[float, Image.Image]:
    """Share of pixels that differ beyond the tolerance, and where."""
    difference = ImageChops.difference(baseline.convert("RGB"), shot.convert("RGB"))
    bands = [band.point(lambda value: 255 if value > CHANNEL_TOLERANCE else 0)
             for band in difference.split()]
    combined = bands[0]
    for band in bands[1:]:
        combined = ImageChops.lighter(combined, band)
    changed = combined.histogram()[255]
    return changed / (baseline.width * baseline.height), combined


def compare(page: Any, browser: Any, name: str, full_page: bool = True) -> None:
    """Assert the page still looks the way the committed baseline says.

    Writes ``<name>.actual.png`` and ``<name>.diff.png`` beside the baseline on
    failure, both ignored by git: the committed file is the one worth keeping.
    """
    import pytest

    directory = baseline_dir(browser)
    baseline_path = directory / f"{name}.png"

    settle(page)
    shot_bytes = page.screenshot(full_page=full_page, mask=_mask_locators(page),
                                 animations="disabled")

    updating = os.environ.get("UPDATE_SCREENSHOTS") == "1"
    if updating or not baseline_path.exists():
        directory.mkdir(parents=True, exist_ok=True)
        baseline_path.write_bytes(shot_bytes)
        # What an earlier failure left for a human to look at describes a
        # baseline that no longer exists.
        (directory / f"{name}.actual.png").unlink(missing_ok=True)
        (directory / f"{name}.diff.png").unlink(missing_ok=True)
        if not updating:
            pytest.skip(
                f"no baseline for {renderer_name(browser)}; one was just written to "
                f"{baseline_path.relative_to(BASELINE_ROOT.parent)} — look at it and "
                f"commit it, and this renderer is covered from then on"
            )
        return

    actual_path = directory / f"{name}.actual.png"
    actual_path.write_bytes(shot_bytes)

    baseline = Image.open(baseline_path)
    shot = Image.open(actual_path)

    assert shot.size == baseline.size, (
        f"{name}: the page is now {shot.size[0]}x{shot.size[1]}, the baseline is "
        f"{baseline.size[0]}x{baseline.size[1]}. Intended? make screenshots"
    )

    share, where = _changed_share(baseline, shot)
    if share > MAX_CHANGED:
        where.save(directory / f"{name}.diff.png")
        raise AssertionError(
            f"{name}: {share:.2%} of pixels changed (limit {MAX_CHANGED:.2%}). "
            f"See {name}.actual.png and {name}.diff.png next to the baseline. "
            f"Intended? make screenshots"
        )

    # Nothing to look at when it passed.
    actual_path.unlink(missing_ok=True)
