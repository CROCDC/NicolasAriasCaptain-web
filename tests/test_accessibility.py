"""Accessibility suite: WCAG 2.2 AA in a real browser, plus what axe cannot see.

Two layers, both against the live server in Chromium:

* **axe-core** (vendored in ``tests/vendor/axe.min.js``) runs the WCAG 2.0-2.2
  A/AA rules and the best-practice rules on every page, on a phone and on a
  desktop, and again in dark mode when the site has one.
* **Behavioural checks** for the criteria a static rule engine cannot judge:
  text size and readability, the user's own font-size setting (1.4.4), reflow at
  320px and in landscape (1.4.10, 1.3.4), text spacing (1.4.12), target size
  (2.5.8), the keyboard path — skip link, every control reachable, focus always
  visible and never hidden under a sticky header, nothing clickable that the
  keyboard cannot reach (2.1.1, 2.4.1, 2.4.7, 2.4.11) — menus and overlays that
  open, trap and close with Escape, reduced motion (2.3.3, 2.2.2), and forms that
  autocomplete and explain their errors (1.3.5, 3.3.1).

Pages are discovered by crawling same-origin links from ``A11Y_PAGES``, plus one
missing URL so the 404 page is held to the same bar.

Run only this file:
    pytest tests/test_accessibility.py -v
Against a deployed site (forms are not submitted there):
    PERF_TARGET_URL=https://the-site.com pytest tests/test_accessibility.py -v
"""

from __future__ import annotations

import os
from collections import deque
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urljoin, urlparse

import pytest
from playwright.sync_api import Browser, Page

# These drive a real Chromium and take seconds; `-m 'not slow'` leaves them out.
pytestmark = pytest.mark.slow

# --- Configuration -----------------------------------------------------------
# Tune per project; the thresholds are the WCAG floor or the common readability
# guidance, not gluck-bags numbers. Relax one only with a reason next to it.

A11Y_PAGES = ["/"]            # crawl seeds
A11Y_MAX_PAGES = 25
A11Y_SKIP_PREFIXES = ("/static/", "/admin", "/panel", "/login", "/logout")
NOT_FOUND_PATH = "/__a11y-missing-page__"

#: Off-site scripts answered with an empty body, so another host's uptime or
#: markup cannot decide a run, e.g. ["**://nexttech.com.ar/**"].
THIRD_PARTY_STUBS: list[str] = ["**://nexttech.com.ar/**"]

#: axe rule id -> why it is accepted. Every entry needs a reason.
AXE_IGNORED_RULES: dict[str, str] = {}
#: CSS selectors axe should not judge (third-party widgets you cannot fix).
AXE_EXCLUDE: list[str] = []

MIN_TEXT_PX = 14              # any visible text
MIN_BODY_TEXT_PX = 16         # running text
BODY_COPY_MIN_CHARS = 80      # what counts as running text
MIN_BODY_LINE_HEIGHT = 1.5
MIN_TARGET_PX = 24            # WCAG 2.5.8 AA, pointer devices
MIN_TOUCH_TARGET_PX = 44      # touch profiles (Apple HIG / WCAG 2.5.5)
USER_FONT_PX = 32             # a user who doubled the browser's default size
MIN_TEXT_GROWTH = 1.5         # at USER_FONT_PX, text must grow at least this much
#: Display type (≥ this size) may be capped by a clamp() and only has to grow
#: noticeably: a 74px headline that reaches 97px is already more than readable.
LARGE_TEXT_PX = 32
MIN_LARGE_TEXT_GROWTH = 1.2
MAX_TAB_STOPS = 250
REDUCED_MOTION_MAX_MS = 50

WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]

PROFILES: dict[str, dict] = {
    "mobile": {"viewport": {"width": 375, "height": 667}, "device_scale_factor": 2,
               "is_mobile": True, "has_touch": True},
    "desktop": {"viewport": {"width": 1280, "height": 800}},
    "reflow-320": {"viewport": {"width": 320, "height": 640}, "device_scale_factor": 2,
                   "is_mobile": True, "has_touch": True},
    "landscape": {"viewport": {"width": 667, "height": 375}, "device_scale_factor": 2,
                  "is_mobile": True, "has_touch": True},
}

TEXT_SPACING_CSS = """
* { line-height: 1.5 !important; letter-spacing: 0.12em !important;
    word-spacing: 0.16em !important; }
p { margin-bottom: 2em !important; }
"""

AXE_PATH = Path(__file__).parent / "vendor" / "axe.min.js"


# --- In-page helpers ---------------------------------------------------------
# One script, injected once per page, so every check shares the same idea of
# "visible" and "selector".

HELPERS_JS = r"""
(() => {
  if (window.__a11y) return;
  const describe = (el) => {
    if (!el || !el.tagName) return String(el);
    let s = el.tagName.toLowerCase();
    if (el.id) return s + '#' + el.id;
    const cls = [...el.classList].slice(0, 3).join('.');
    if (cls) s += '.' + cls;
    const parent = el.parentElement;
    if (parent && !cls) s = describe(parent) + ' > ' + s;
    return s;
  };
  const visuallyHidden = (el) => {
    for (let node = el; node && node !== document.documentElement; node = node.parentElement) {
      const cs = getComputedStyle(node);
      if (cs.display === 'none') return true;
      if (cs.clip === 'rect(0px, 0px, 0px, 0px)' || cs.clipPath === 'inset(50%)') return true;
      if (cs.overflow !== 'visible' && node.offsetWidth <= 1 && node.offsetHeight <= 1) return true;
    }
    return false;
  };
  const effectiveOpacity = (el) => {
    let o = 1;
    for (let node = el; node && node.nodeType === 1; node = node.parentElement) {
      o *= parseFloat(getComputedStyle(node).opacity);
    }
    return o;
  };
  const shown = (el) => {
    if (!el || el.closest('[aria-hidden="true"], [inert], script, style, noscript, template')) {
      return false;
    }
    const cs = getComputedStyle(el);
    if (cs.visibility !== 'visible' || visuallyHidden(el)) return false;
    const r = el.getBoundingClientRect();
    if (r.width < 1 || r.height < 1) return false;
    if (r.right <= 0 || r.bottom + scrollY <= 0) return false;
    return effectiveOpacity(el) > 0.05;
  };
  const textRuns = () => {
    const runs = [];
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    for (let n = walker.nextNode(); n; n = walker.nextNode()) {
      const text = n.textContent.trim();
      const el = n.parentElement;
      if (!text || !shown(el)) continue;
      let size = parseFloat(getComputedStyle(el).fontSize);
      const svg = el instanceof SVGElement;
      if (svg && el.getScreenCTM) {
        const m = el.getScreenCTM();
        if (m) size *= Math.hypot(m.a, m.b);
      }
      runs.push({selector: describe(el), text: text.slice(0, 50), size, svg});
    }
    return runs;
  };
  const focusables = () => [...document.querySelectorAll(
    'a[href], button, input:not([type="hidden"]), select, textarea, summary, iframe, ' +
    '[tabindex]:not([tabindex="-1"]), [contenteditable="true"]')]
    .filter((el) => !el.disabled && shown(el));
  const overflowsViewport = () => {
    const out = [];
    const width = document.documentElement.clientWidth;
    if (document.documentElement.scrollWidth > width + 1) {
      out.push('page scrolls sideways: scrollWidth ' + document.documentElement.scrollWidth +
               ' > ' + width);
    }
    for (const el of document.body.querySelectorAll('*')) {
      const own = [...el.childNodes].some((c) => c.nodeType === 3 && c.textContent.trim());
      if (!own || !shown(el)) continue;
      const r = el.getBoundingClientRect();
      if (r.right <= width + 1 && r.left >= -1) continue;
      let clipped = false;
      for (let p = el.parentElement; p && p !== document.body; p = p.parentElement) {
        const cs = getComputedStyle(p);
        if (cs.overflowX !== 'visible' || cs.position === 'fixed') { clipped = true; break; }
      }
      if (!clipped) out.push(describe(el) + ' runs off-screen ("' +
                             el.textContent.trim().slice(0, 30) + '")');
    }
    return out;
  };
  const clippedText = () => {
    const out = [];
    for (const el of document.body.querySelectorAll('*')) {
      const own = [...el.childNodes].some((c) => c.nodeType === 3 && c.textContent.trim());
      if (!own || !shown(el)) continue;
      const cs = getComputedStyle(el);
      const hides = /hidden|clip/.test(cs.overflowX + ' ' + cs.overflowY);
      const ellipsis = cs.textOverflow === 'ellipsis' || cs.webkitLineClamp !== 'none';
      if (!hides && !ellipsis) continue;
      if (el.scrollWidth > el.clientWidth + 2 || el.scrollHeight > el.clientHeight + 2) {
        out.push(describe(el) + ' cuts its text ("' + el.textContent.trim().slice(0, 30) + '")');
      }
    }
    return out;
  };
  const overlappingText = () => {
    const boxes = [];
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    for (let n = walker.nextNode(); n; n = walker.nextNode()) {
      const el = n.parentElement;
      if (!n.textContent.trim() || !shown(el) || el instanceof SVGElement) continue;
      const range = document.createRange();
      range.selectNodeContents(n);
      for (const r of range.getClientRects()) {
        if (r.width > 1 && r.height > 1) boxes.push({el, r});
      }
    }
    const out = new Set();
    for (let i = 0; i < boxes.length; i++) {
      for (let j = i + 1; j < boxes.length; j++) {
        const a = boxes[i], b = boxes[j];
        if (a.el === b.el || a.el.contains(b.el) || b.el.contains(a.el)) continue;
        const w = Math.min(a.r.right, b.r.right) - Math.max(a.r.left, b.r.left);
        const h = Math.min(a.r.bottom, b.r.bottom) - Math.max(a.r.top, b.r.top);
        if (w > 2 && h > 2) out.add(describe(a.el) + ' overlaps ' + describe(b.el));
      }
    }
    return [...out];
  };
  window.__a11y = {describe, shown, textRuns, focusables, overflowsViewport, clippedText,
                   overlappingText, effectiveOpacity};
})();
"""

SETTLE_JS = """
async () => {
  await document.fonts.ready;
  const pause = (ms) => new Promise((r) => setTimeout(r, ms));
  const step = Math.max(200, innerHeight * 0.7);
  for (let y = 0; y < document.documentElement.scrollHeight; y += step) {
    scrollTo({top: y, behavior: 'instant'});
    await pause(60);
  }
  scrollTo({top: 0, behavior: 'instant'});
  const finite = document.getAnimations().filter((a) => {
    const t = a.effect && a.effect.getComputedTiming();
    return t && Number.isFinite(t.endTime);
  });
  await Promise.race([Promise.all(finite.map((a) => a.finished.catch(() => null))), pause(3000)]);
  await pause(100);
}
"""


# --- Fixtures ----------------------------------------------------------------

def _is_remote() -> bool:
    return bool(os.environ.get("PERF_TARGET_URL"))


@pytest.fixture(scope="session")
def axe_source() -> str:
    assert AXE_PATH.exists(), f"axe-core is missing: expected {AXE_PATH}"
    return AXE_PATH.read_text()


@contextmanager
def opened(browser: Browser, url: str, profile: str, settle: bool = True,
           **context_options) -> Iterator[Page]:
    """A fresh context on ``url`` under a profile, scrolled through and settled.

    Scrolling first matters: reveal-on-scroll and lazy content are only in
    their final state once they have been in view, and that final state is what
    a reader gets.
    """
    # bypass_csp: axe and the helpers are injected inline, which a strict CSP
    # would block; it changes nothing the page itself renders.
    context = browser.new_context(**PROFILES[profile], bypass_csp=True, **context_options)
    try:
        for pattern in THIRD_PARTY_STUBS:
            context.route(pattern, lambda route: route.fulfill(
                status=200, content_type="application/javascript", body=""))
        page = context.new_page()
        page.goto(url, wait_until="networkidle")
        if settle:
            page.evaluate(SETTLE_JS)
        page.evaluate(HELPERS_JS)
        yield page
    finally:
        context.close()


@pytest.fixture(scope="session")
def site_pages(browser: Browser, live_server: str) -> list[str]:
    """Every same-origin page reachable from the seeds, plus the 404 page."""
    origin = urlparse(live_server).netloc
    seen: list[str] = []
    queue = deque(A11Y_PAGES)
    context = browser.new_context()
    try:
        for pattern in THIRD_PARTY_STUBS:
            context.route(pattern, lambda route: route.fulfill(
                status=200, content_type="application/javascript", body=""))
        page = context.new_page()
        while queue and len(seen) < A11Y_MAX_PAGES:
            path = queue.popleft()
            if path in seen:
                continue
            response = page.goto(live_server + path, wait_until="domcontentloaded")
            if response is None or not response.ok:
                continue
            seen.append(path)
            for href in page.eval_on_selector_all("a[href]", "els => els.map(a => a.href)"):
                url = urlparse(urljoin(live_server + path, href))
                if url.scheme not in ("http", "https") or url.netloc != origin:
                    continue
                link = url.path or "/"
                if link.startswith(A11Y_SKIP_PREFIXES) or "." in link.rsplit("/", 1)[-1]:
                    continue
                if link not in seen and link not in queue:
                    queue.append(link)
    finally:
        context.close()
    assert seen, f"no page answered among the seeds {A11Y_PAGES}"
    return seen + [NOT_FOUND_PATH]


def _run_axe(page: Page, axe_source: str, tags: list[str], include: str | None = None) -> list:
    if not page.evaluate("() => !!window.axe"):
        page.add_script_tag(content=axe_source)
    context: dict = {"exclude": [[sel] for sel in AXE_EXCLUDE]}
    if include:
        context["include"] = [[include]]
    options = {"runOnly": {"type": "tag", "values": tags}, "resultTypes": ["violations"]}
    result = page.evaluate("([c, o]) => axe.run(c, o)", [context, options])
    return [v for v in result["violations"] if v["id"] not in AXE_IGNORED_RULES]


def _describe_axe(where: str, violations: list) -> list[str]:
    lines = []
    for v in violations:
        lines.append(f"{where}: [{v['impact']}] {v['id']} — {v['help']} ({v['helpUrl']})")
        for node in v["nodes"][:6]:
            summary = (node.get("failureSummary") or "").strip().splitlines()
            lines.append(f"      {node['target']}  {summary[-1].strip() if summary else ''}")
        if len(v["nodes"]) > 6:
            lines.append(f"      … and {len(v['nodes']) - 6} more")
    return lines


def _supports_dark(page: Page) -> bool:
    return page.evaluate("""() => [...document.styleSheets].some((sheet) => {
        try { return [...sheet.cssRules].some((r) => r.media &&
                     r.media.mediaText.includes('prefers-color-scheme: dark')); }
        catch (e) { return false; } })""")


def _report(problems: list[str], headline: str) -> str:
    return f"{headline} ({len(problems)}):\n" + "\n".join(problems[:80])


# --- axe ---------------------------------------------------------------------

@pytest.mark.parametrize("profile", ["mobile", "desktop"])
def test_wcag_aa_rules_pass(browser, live_server, site_pages, axe_source, profile):
    problems: list[str] = []
    for path in site_pages:
        with opened(browser, live_server + path, profile) as page:
            problems += _describe_axe(f"{path} [{profile}]",
                                      _run_axe(page, axe_source, WCAG_TAGS))
            if _supports_dark(page):
                page.emulate_media(color_scheme="dark")
                page.evaluate(SETTLE_JS)
                problems += _describe_axe(f"{path} [{profile}, dark]",
                                          _run_axe(page, axe_source, WCAG_TAGS))
    assert not problems, _report(problems, "WCAG 2.2 AA violations")


@pytest.mark.parametrize("profile", ["mobile", "desktop"])
def test_best_practice_rules_pass(browser, live_server, site_pages, axe_source, profile):
    problems: list[str] = []
    for path in site_pages:
        with opened(browser, live_server + path, profile) as page:
            problems += _describe_axe(f"{path} [{profile}]",
                                      _run_axe(page, axe_source, ["best-practice"]))
    assert not problems, _report(problems, "axe best-practice violations")


# --- Reading -----------------------------------------------------------------

@pytest.mark.parametrize("profile", ["mobile", "desktop"])
def test_no_text_is_too_small(browser, live_server, site_pages, profile):
    problems: set[str] = set()
    for path in site_pages:
        with opened(browser, live_server + path, profile) as page:
            for run in page.evaluate("() => __a11y.textRuns()"):
                if run["size"] < MIN_TEXT_PX - 0.05:
                    problems.add(f"{path}: {run['size']:.1f}px {run['selector']} "
                                 f"(\"{run['text']}\")")
    assert not problems, _report(sorted(problems), f"Text smaller than {MIN_TEXT_PX}px")


@pytest.mark.parametrize("profile", ["mobile", "desktop", "landscape"])
def test_no_text_overlaps_other_text(browser, live_server, site_pages, profile):
    """Two runs of text drawn over each other are unreadable, whatever their size."""
    problems: list[str] = []
    for path in site_pages:
        with opened(browser, live_server + path, profile) as page:
            problems += [f"{path} [{profile}]: {p}"
                         for p in page.evaluate("() => __a11y.overlappingText()")]
    assert not problems, _report(problems, "Overlapping text")


@pytest.mark.parametrize("profile", ["mobile", "desktop"])
def test_running_text_is_comfortable_to_read(browser, live_server, site_pages, profile):
    problems: list[str] = []
    for path in site_pages:
        with opened(browser, live_server + path, profile) as page:
            blocks = page.evaluate(
                """(minChars) => [...document.querySelectorAll(
                    'p, li, dd, blockquote, td, figcaption, address')]
                .filter((el) => __a11y.shown(el) && el.textContent.trim().length >= minChars)
                .map((el) => {
                    const cs = getComputedStyle(el);
                    const size = parseFloat(cs.fontSize);
                    const lh = cs.lineHeight === 'normal' ? 1.2 : parseFloat(cs.lineHeight) / size;
                    return {selector: __a11y.describe(el), size, lh}; })""",
                BODY_COPY_MIN_CHARS)
            for b in blocks:
                if b["size"] < MIN_BODY_TEXT_PX - 0.05:
                    problems.append(f"{path}: {b['selector']} running text at {b['size']:.1f}px "
                                    f"(< {MIN_BODY_TEXT_PX}px)")
                if b["lh"] < MIN_BODY_LINE_HEIGHT - 0.01:
                    problems.append(f"{path}: {b['selector']} line-height {b['lh']:.2f} "
                                    f"(< {MIN_BODY_LINE_HEIGHT})")
    assert not problems, _report(problems, "Running text that is hard to read")


def test_text_follows_the_users_font_size(browser, live_server, site_pages):
    """WCAG 1.4.4: a reader who sets a larger default size gets larger text.

    A root ``font-size`` in px, or type set in px or vw, ignores that setting
    — browser zoom still works, but the reader's own preference does not.
    """
    problems: list[str] = []
    for path in site_pages:
        with opened(browser, live_server + path, "desktop") as page:
            before = {(r["selector"], r["text"]): r["size"]
                      for r in page.evaluate("() => __a11y.textRuns()")}
            cdp = page.context.new_cdp_session(page)
            cdp.send("Page.setFontSizes", {"fontSizes": {"standard": USER_FONT_PX,
                                                         "fixed": USER_FONT_PX}})
            page.reload(wait_until="networkidle")
            page.evaluate(SETTLE_JS)
            page.evaluate(HELPERS_JS)
            root = page.evaluate("() => parseFloat(getComputedStyle(document.documentElement)"
                                 ".fontSize)")
            if abs(root - USER_FONT_PX) > 0.5:
                problems.append(f"{path}: root font-size stays {root:.0f}px when the user "
                                f"asks for {USER_FONT_PX}px — set it in % or rem, not px")
            stuck: set[str] = set()
            for run in page.evaluate("() => __a11y.textRuns()"):
                old = before.get((run["selector"], run["text"]))
                growth = MIN_LARGE_TEXT_GROWTH if old and old >= LARGE_TEXT_PX else MIN_TEXT_GROWTH
                if old and not run["svg"] and run["size"] < old * growth:
                    stuck.add(f"{run['selector']} {old:.0f}px → {run['size']:.0f}px")
            problems += [f"{path}: text does not grow: {s}" for s in sorted(stuck)]
            problems += [f"{path} @ {USER_FONT_PX}px: {p}"
                         for p in page.evaluate("() => __a11y.overflowsViewport()")]
            problems += [f"{path} @ {USER_FONT_PX}px: {p}"
                         for p in page.evaluate("() => __a11y.clippedText()")]
            problems += [f"{path} @ {USER_FONT_PX}px: {p}"
                         for p in page.evaluate("() => __a11y.overlappingText()")]
    assert not problems, _report(problems, "Text that ignores the user's font size")


@pytest.mark.parametrize("profile", ["reflow-320", "landscape"])
def test_content_reflows_without_sideways_scrolling(browser, live_server, site_pages, profile):
    """WCAG 1.4.10 (320 CSS px) and 1.3.4 (a phone held sideways)."""
    problems: list[str] = []
    for path in site_pages:
        with opened(browser, live_server + path, profile) as page:
            problems += [f"{path} [{profile}]: {p}"
                         for p in page.evaluate("() => __a11y.overflowsViewport()")]
            problems += [f"{path} [{profile}]: {p}"
                         for p in page.evaluate("() => __a11y.clippedText()")]
            problems += [f"{path} [{profile}]: {p}"
                         for p in page.evaluate("() => __a11y.overlappingText()")]
    assert not problems, _report(problems, "Content that does not reflow")


@pytest.mark.parametrize("profile", ["mobile", "desktop"])
def test_text_survives_user_spacing(browser, live_server, site_pages, profile):
    """WCAG 1.4.12: the bookmarklet spacing must not cut or spill any text."""
    problems: list[str] = []
    for path in site_pages:
        with opened(browser, live_server + path, profile) as page:
            page.add_style_tag(content=TEXT_SPACING_CSS)
            page.wait_for_timeout(150)
            problems += [f"{path} [{profile}]: {p}"
                         for p in page.evaluate("() => __a11y.clippedText()")]
            problems += [f"{path} [{profile}]: {p}"
                         for p in page.evaluate("() => __a11y.overflowsViewport()")]
            problems += [f"{path} [{profile}]: {p}"
                         for p in page.evaluate("() => __a11y.overlappingText()")]
    assert not problems, _report(problems, "Text that breaks under WCAG text spacing")


# --- Pointer -----------------------------------------------------------------

@pytest.mark.parametrize("profile", ["mobile", "desktop"])
def test_targets_are_big_enough(browser, live_server, site_pages, profile):
    """WCAG 2.5.8 on a pointer; the 44px touch size on a phone.

    Links inside a sentence are exempt, as WCAG exempts them: their size is the
    text's, and the text is held to its own minimum above.
    """
    minimum = MIN_TOUCH_TARGET_PX if PROFILES[profile].get("has_touch") else MIN_TARGET_PX
    problems: set[str] = set()
    for path in site_pages:
        with opened(browser, live_server + path, profile) as page:
            small = page.evaluate(
                """(minimum) => __a11y.focusables().filter((el) => {
                    if (el.tagName === 'A' && getComputedStyle(el).display === 'inline') {
                        const block = el.parentElement.closest('p, li, dd, td, blockquote');
                        if (block && block.textContent.trim().length >
                                el.textContent.trim().length + 20) return false;
                    }
                    const r = el.getBoundingClientRect();
                    return r.width < minimum - 0.5 || r.height < minimum - 0.5;
                }).map((el) => {
                    const r = el.getBoundingClientRect();
                    const size = `${Math.round(r.width)}x${Math.round(r.height)}`;
                    return `${__a11y.describe(el)} ${size}`; })""",
                minimum)
            problems |= {f"{path} [{profile}]: {s}" for s in small}
    assert not problems, _report(sorted(problems), f"Targets smaller than {minimum}px")


# --- Keyboard ----------------------------------------------------------------

STOP_JS = """
async () => {
  const el = document.activeElement;
  if (!el || el === document.body) return null;
  // Under scroll-behavior: smooth the page is still gliding towards the focused
  // element; judge it where the reader sees it, once the scroll has stopped.
  const frame = () => new Promise((r) => requestAnimationFrame(r));
  for (let still = 0, last = -1, i = 0; still < 3 && i < 120; i++) {
    await frame();
    still = scrollY === last ? still + 1 : 0;
    last = scrollY;
  }
  const r = el.getBoundingClientRect();
  const xs = [r.left + 2, r.left + r.width / 2, r.right - 2];
  const ys = [r.top + 2, r.top + r.height / 2, r.bottom - 2];
  let seen = false;
  for (const x of xs) for (const y of ys) {
    if (x < 0 || y < 0 || x >= innerWidth || y >= innerHeight) continue;
    const hit = document.elementFromPoint(x, y);
    if (hit && (hit === el || el.contains(hit) || hit.contains(el))) seen = true;
  }
  if (!el.dataset.a11yStop) el.dataset.a11yStop = String(document.querySelectorAll(
      '[data-a11y-stop]').length + 1);
  return {id: el.dataset.a11yStop, selector: __a11y.describe(el), seen,
          box: {x: Math.max(0, r.left - 6), y: Math.max(0, r.top - 6),
                width: Math.min(innerWidth, r.width + 12),
                height: Math.min(innerHeight, r.height + 12)}};
}
"""


def _tab_walk(page: Page) -> list[dict]:
    """Tab through the page once, screenshotting each stop focused and blurred."""
    stops: list[dict] = []
    for _ in range(MAX_TAB_STOPS):
        page.keyboard.press("Tab")
        stop = page.evaluate(STOP_JS)
        if stop is None:
            continue
        if stops and stop["id"] == stops[0]["id"]:
            break
        box = stop["box"]
        if box["width"] >= 1 and box["height"] >= 1 and stop["seen"]:
            focused = page.screenshot(clip=box, animations="disabled")
            page.evaluate("() => document.activeElement.blur()")
            blurred = page.screenshot(clip=box, animations="disabled")
            # Chromium keeps the sequential-focus starting point on the blurred
            # element, so the next Tab still moves on from here.
            stop["indicator"] = focused != blurred
        stops.append(stop)
    return stops


def test_keyboard_reaches_every_control_with_visible_focus(browser, live_server, site_pages):
    """WCAG 2.1.1, 2.4.3, 2.4.7 and 2.4.11 along the real Tab order."""
    problems: list[str] = []
    for path in site_pages:
        with opened(browser, live_server + path, "desktop") as page:
            page.evaluate("() => __a11y.focusables().forEach((el, i) => "
                          "el.dataset.a11yControl = String(i))")
            stops = _tab_walk(page)
            reached = set(page.eval_on_selector_all(
                "[data-a11y-stop][data-a11y-control]",
                "els => els.map(e => e.dataset.a11yControl)"))
            missed = page.evaluate("""(reached) => [...document.querySelectorAll(
                    '[data-a11y-control]')].filter((el) => !reached.includes(el.dataset.a11yControl)
                    && el.tabIndex >= 0).map((el) => __a11y.describe(el))""", sorted(reached))
            problems += [f"{path}: not reachable with Tab: {m}" for m in missed]
            for stop in stops:
                if not stop["seen"]:
                    problems.append(f"{path}: focus is hidden (off-screen or under another "
                                    f"element) on {stop['selector']}")
                elif stop.get("indicator") is False:
                    problems.append(f"{path}: no visible focus indicator on {stop['selector']}")
            mouse_only = page.evaluate("""() => [...document.body.querySelectorAll('*')]
                .filter((el) => __a11y.shown(el) && getComputedStyle(el).cursor === 'pointer'
                    && !el.closest('a[href], button, input, select, textarea, summary, label, '
                                   + '[tabindex]:not([tabindex="-1"]), [contenteditable="true"]'))
                .filter((el) => !el.parentElement || getComputedStyle(el.parentElement).cursor
                    !== 'pointer')
                .map((el) => __a11y.describe(el))""")
            problems += [f"{path}: clickable but not keyboard-operable: {m}" for m in mouse_only]
    assert not problems, _report(problems, "Keyboard problems")


def test_skip_link_jumps_to_the_content(browser, live_server, site_pages):
    """WCAG 2.4.1: the first Tab offers a visible way past the repeated header.

    A page whose first stop is already inside ``<main>`` has nothing to skip.
    """
    problems: list[str] = []
    for path in site_pages:
        with opened(browser, live_server + path, "desktop") as page:
            page.keyboard.press("Tab")
            first = page.evaluate("""() => { const el = document.activeElement;
                const href = el && el.getAttribute('href') || '';
                const target = href.startsWith('#') && href.length > 1 &&
                    document.getElementById(decodeURIComponent(href.slice(1)));
                const r = el.getBoundingClientRect();
                return {selector: __a11y.describe(el), href, target: !!target,
                        inMain: !!el.closest('main, [role="main"]'),
                        visible: r.width > 1 && r.height > 1 && r.left >= 0 && r.top >= 0
                                 && r.right <= innerWidth && r.bottom <= innerHeight}; }""")
            if first["inMain"]:
                continue
            if not first["href"].startswith("#"):
                problems.append(f"{path}: first Tab lands on {first['selector']}, not a skip link")
                continue
            if not first["target"]:
                problems.append(f"{path}: skip link {first['href']} points at nothing")
            if not first["visible"]:
                problems.append(f"{path}: skip link is focused but not visible on screen")
            page.keyboard.press("Enter")
            page.wait_for_timeout(300)
            page.keyboard.press("Tab")
            landed = page.evaluate(
                """(href) => {
                    const target = document.getElementById(decodeURIComponent(href.slice(1)));
                    const el = document.activeElement;
                    const after = Node.DOCUMENT_POSITION_FOLLOWING;
                    return !!target && (target.contains(el) ||
                        !!(target.compareDocumentPosition(el) & after)); }""",
                first["href"])
            if not landed:
                problems.append(f"{path}: after the skip link, Tab goes back into the header")
    assert not problems, _report(problems, "Skip link problems")


@pytest.mark.parametrize("profile", ["mobile", "desktop"])
def test_disclosures_open_and_close_from_the_keyboard(browser, live_server, site_pages,
                                                      axe_source, profile):
    """Every ``aria-expanded`` control opens with Enter and reports it.

    One that covers the screen is a dialog in all but name: focus goes in,
    stays in while it is open, Escape closes it and focus comes back.
    """
    problems: list[str] = []
    for path in site_pages:
        with opened(browser, live_server + path, profile) as page:
            count = page.evaluate("""() => { const all = [...document.querySelectorAll(
                    '[aria-expanded="false"]')].filter((el) => __a11y.shown(el));
                all.forEach((el, i) => el.dataset.a11yToggle = String(i)); return all.length; }""")
            for i in range(count):
                toggle = page.locator(f'[data-a11y-toggle="{i}"]')
                name = page.evaluate("(el) => __a11y.describe(el)", toggle.element_handle())
                controls = toggle.get_attribute("aria-controls")
                if not controls or page.locator(f"#{controls}").count() == 0:
                    problems.append(f"{path} [{profile}]: {name} has aria-expanded but no "
                                    f"aria-controls pointing at what it opens")
                    continue
                toggle.focus()
                page.keyboard.press("Enter")
                page.wait_for_timeout(600)
                if toggle.get_attribute("aria-expanded") != "true":
                    problems.append(f"{path} [{profile}]: Enter on {name} leaves "
                                    f"aria-expanded=false")
                    continue
                panel = page.evaluate(
                    """(id) => {
                        const el = document.getElementById(id);
                        const r = el.getBoundingClientRect();
                        const cs = getComputedStyle(el);
                        const covers = r.width * r.height > innerWidth * innerHeight * 0.5;
                        return {shown: __a11y.shown(el),
                                overlay: ['fixed', 'absolute'].includes(cs.position) && covers,
                                focusInside: el.contains(document.activeElement)}; }""",
                    controls)
                if not panel["shown"]:
                    problems.append(f"{path} [{profile}]: {name} says expanded but #{controls} "
                                    f"is not visible")
                    continue
                problems += _describe_axe(f"{path} [{profile}, #{controls} open]",
                                          _run_axe(page, axe_source, WCAG_TAGS, f"#{controls}"))
                if panel["overlay"]:
                    if not panel["focusInside"]:
                        problems.append(f"{path} [{profile}]: opening #{controls} leaves focus "
                                        f"behind it")
                    for _ in range(30):
                        page.keyboard.press("Tab")
                        inside = page.evaluate("(id) => document.getElementById(id)"
                                               ".contains(document.activeElement)", controls)
                        if not inside:
                            problems.append(f"{path} [{profile}]: Tab escapes the open "
                                            f"#{controls} into the page behind it")
                            break
                    page.keyboard.press("Escape")
                    page.wait_for_timeout(600)
                    if toggle.get_attribute("aria-expanded") != "false":
                        problems.append(f"{path} [{profile}]: Escape does not close #{controls}")
                    elif not page.evaluate("(el) => el === document.activeElement",
                                           toggle.element_handle()):
                        problems.append(f"{path} [{profile}]: closing #{controls} does not "
                                        f"return focus to {name}")
                else:
                    toggle.focus()
                    page.keyboard.press("Enter")
                    page.wait_for_timeout(600)
                    if toggle.get_attribute("aria-expanded") != "false":
                        problems.append(f"{path} [{profile}]: Enter again does not close "
                                        f"#{controls}")
    assert not problems, _report(problems, "Disclosure / overlay problems")


# --- Motion ------------------------------------------------------------------

def test_reduced_motion_is_respected(browser, live_server, site_pages):
    """With reduced motion asked for: nothing moves, nothing autoplays, nothing is
    left invisible waiting for an animation that will not come."""
    problems: list[str] = []
    for path in site_pages:
        with opened(browser, live_server + path, "mobile", settle=False,
                    reduced_motion="reduce") as page:
            moving = page.evaluate("""async (maxMs) => {
                const seen = new Set();
                const step = Math.max(200, innerHeight * 0.7);
                for (let y = 0; y < document.documentElement.scrollHeight; y += step) {
                    scrollTo({top: y, behavior: 'instant'});
                    await new Promise((r) => setTimeout(r, 80));
                    for (const a of document.getAnimations()) {
                        const t = a.effect && a.effect.getComputedTiming();
                        const target = a.effect && a.effect.target;
                        if (!t || a.playState !== 'running') continue;
                        if (!Number.isFinite(t.endTime) || t.activeDuration > maxMs) {
                            const what = a.animationName || a.transitionProperty || 'animation';
                            const who = target ? __a11y.describe(target) : 'document';
                            seen.add(`${who} (${what})`);
                        }
                    }
                }
                return [...seen]; }""", REDUCED_MOTION_MAX_MS)
            problems += [f"{path}: still animates under reduced motion: {m}" for m in moving]
            if page.evaluate("() => getComputedStyle(document.documentElement).scrollBehavior"
                             " === 'smooth'"):
                problems.append(f"{path}: smooth scrolling stays on under reduced motion")
            playing = page.evaluate("""() => [...document.querySelectorAll('video')]
                .filter((v) => !v.paused && __a11y.shown(v)).map((v) => __a11y.describe(v))""")
            problems += [f"{path}: video plays by itself under reduced motion: {v}"
                         for v in playing]
            page.wait_for_timeout(200)
            hidden = page.evaluate("""() => [...document.body.querySelectorAll('*')].filter((el) =>
                    [...el.childNodes].some((c) => c.nodeType === 3 && c.textContent.trim())
                    && getComputedStyle(el).visibility === 'visible'
                    && !el.closest('[aria-hidden="true"], [hidden], [inert]')
                    && el.getBoundingClientRect().width > 1
                    && __a11y.effectiveOpacity(el) < 0.05)
                .map((el) => __a11y.describe(el))""")
            problems += [f"{path}: text left invisible: {h}" for h in hidden]
    assert not problems, _report(problems, "Reduced-motion problems")


def test_autoplaying_media_can_be_paused(browser, live_server, site_pages):
    """WCAG 2.2.2: moving media longer than 5s needs a control."""
    problems: list[str] = []
    for path in site_pages:
        with opened(browser, live_server + path, "desktop") as page:
            problems += [f"{path}: {v}" for v in page.evaluate("""() =>
                [...document.querySelectorAll('video[autoplay], audio[autoplay]')]
                .filter((m) => (m.loop || !(m.duration <= 5)) && !m.controls &&
                    !(m.id && document.querySelector(`[aria-controls~="${m.id}"]`)))
                .map((m) => __a11y.describe(m) + ' autoplays with no way to pause it')""")]
    assert not problems, _report(problems, "Autoplaying media")


# --- Forms -------------------------------------------------------------------

AUTOCOMPLETE_HINTS = {
    "email": ("email", "mail", "correo"),
    "tel": ("tel", "phone", "telefono", "teléfono", "celular", "whatsapp"),
    "name": ("name", "nombre", "fullname"),
}


def test_forms_autocomplete_and_explain_their_errors(browser, live_server, site_pages):
    """WCAG 1.3.5 (personal data autocompletes) and 3.3.1 (errors are told).

    The empty-submit half only runs locally: against a deployed site it would
    post to production.
    """
    problems: list[str] = []
    for path in site_pages:
        with opened(browser, live_server + path, "desktop") as page:
            fields = page.evaluate("""() => [...document.querySelectorAll(
                    'form input:not([type=hidden]):not([type=submit]):not([type=checkbox])'
                    + ':not([type=radio])')].filter((el) => __a11y.shown(el)).map((el) => ({
                    selector: __a11y.describe(el), type: el.type,
                    key: (el.name + ' ' + el.id).toLowerCase(),
                    autocomplete: (el.getAttribute('autocomplete') || '').toLowerCase()}))""")
            for f in fields:
                for token, hints in AUTOCOMPLETE_HINTS.items():
                    wants = f["type"] == token or any(h in f["key"] for h in hints)
                    if wants and (not f["autocomplete"] or f["autocomplete"] == "off"):
                        problems.append(f"{path}: {f['selector']} looks like {token} but has "
                                        f"no autocomplete=\"{token}\"")
                        break
            if _is_remote():
                continue
            for index in range(page.locator("form").count()):
                form = page.locator("form").nth(index)
                if not form.is_visible():
                    continue
                submit = form.locator("button[type=submit], button:not([type]), "
                                      "input[type=submit]").first
                if submit.count() == 0:
                    continue
                native = form.get_attribute("novalidate") is None
                submit.click()
                page.wait_for_timeout(800)
                page.evaluate(HELPERS_JS)
                state = page.evaluate("""() => {
                    const invalid = [...document.querySelectorAll('[aria-invalid="true"]')];
                    const told = invalid.filter((el) => {
                        const refs = (el.getAttribute('aria-describedby') || '') + ' ' +
                                     (el.getAttribute('aria-errormessage') || '');
                        const ids = refs.trim().split(/\\s+/);
                        return ids.some((id) => { const m = id && document.getElementById(id);
                            return m && m.textContent.trim() && __a11y.shown(m); }); });
                    const active = document.activeElement;
                    const nativeInvalid = active && active.matches && active.matches(':invalid');
                    const announced = [...document.querySelectorAll(
                        '[role=alert], [aria-live=assertive], [aria-live=polite], [role=status]')]
                        .some((el) => el.textContent.trim());
                    return {invalid: invalid.map((el) => __a11y.describe(el)),
                            untold: invalid.filter((el) => !told.includes(el))
                                           .map((el) => __a11y.describe(el)),
                            focusOnInvalid: !!active && (active.getAttribute('aria-invalid')
                                === 'true' || !!nativeInvalid), nativeInvalid: !!nativeInvalid,
                            announced}; }""")
                if native and state["nativeInvalid"]:
                    continue
                if not state["invalid"]:
                    problems.append(f"{path}: submitting form #{index} empty marks no field "
                                    f"aria-invalid")
                    continue
                problems += [f"{path}: {s} is aria-invalid with no error text tied to it "
                             f"(aria-describedby / aria-errormessage)" for s in state["untold"]]
                if not (state["focusOnInvalid"] or state["announced"]):
                    problems.append(f"{path}: form #{index} errors are neither focused nor "
                                    f"announced (role=alert / aria-live)")
    assert not problems, _report(problems, "Form problems")
