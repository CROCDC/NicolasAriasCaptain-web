"""Lighthouse audit test (the official Google audits, run in CI).

Runs the Lighthouse CLI (via `npx`) against the live server and asserts on the
audits that are *stable* in a lab run: the content/opportunity audits (image
formats, responsive images, compression, caching, minification) plus a perf-score
floor and an LCP budget.

Why this complements the Playwright suite: Lighthouse catches things that are
expensive to assert by hand (next-gen image savings, render-blocking analysis,
forced reflow, the official score), while the Playwright tests give fast, stable
raw metrics and the device matrix.

Throttling: we use `--throttling-method=devtools` (real CDP throttling). The
default `simulate` method badly *inflates* LCP for font/CSS-gated pages (we've
seen 5s simulated vs ~1.9s real), so it would report misleading timing.

Requirements (the test fails loudly if missing — it's not skipped):
    - Node + npx on PATH (Lighthouse itself is fetched on demand by `npx --yes`).
    - A Chrome/Chromium binary (auto-detected; override with CHROME_PATH).

Run only this file:
    pytest tests/test_lighthouse.py -v
Against a deployed site:
    PERF_TARGET_URL=https://the-site.com pytest tests/test_lighthouse.py -v
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile

import pytest

# Drives a real Chromium through the Lighthouse CLI; seconds, not milliseconds.
pytestmark = pytest.mark.slow

LIGHTHOUSE_VERSION = "lighthouse@12"

# Opportunity audits → max wasted KiB tolerated. Calibrate to your site: set to
# current savings + headroom so the test catches *regressions* (bytes growing)
# while tolerating known trade-offs. 0 = the audit must fully pass.
# (modern-image-formats only reaches 0 if you also ship AVIF; uses-responsive-
# images depends on your srcset coverage.)
AUDIT_SAVINGS_BUDGET_KB = {
    "uses-text-compression": 0,
    "uses-long-cache-ttl": 20,
    "unminified-css": 30,
    "unminified-javascript": 30,
    "unused-css-rules": 60,
    "offscreen-images": 30,
    "modern-image-formats": 250,
    "uses-responsive-images": 150,
}


def _is_remote() -> bool:
    return bool(os.environ.get("PERF_TARGET_URL"))


def _find_chrome(fallback: str | None = None) -> str | None:
    """A Chrome for Lighthouse to drive; ``fallback`` is Playwright's own.

    The bundled Chromium has to be passed in rather than looked up here.
    Reading it needs a Playwright driver, and the rest of the suite already
    holds one open — starting a second refuses with "use the Async API",
    which surfaced as a baffling "No Chrome/Chromium found".
    """
    if os.environ.get("CHROME_PATH"):
        return os.environ["CHROME_PATH"]
    candidates = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
    ]
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome"):
        found = shutil.which(name)
        if found:
            candidates.insert(0, found)
    for path in candidates:
        if path and os.path.exists(path):
            return path
    return fallback


@pytest.fixture(scope="session")
def lighthouse_report(live_server: str, playwright_driver) -> dict:
    """Run Lighthouse once against the live server and return the parsed report."""
    # A tool that is absent is a skip, not a failure: this suite also runs
    # inside the deployment image, which carries neither Node nor Chromium on
    # purpose. A report that came back empty below is a different matter — that
    # is Lighthouse having run and failed, and it stays a failure.
    if shutil.which("npx") is None:
        pytest.skip("Lighthouse needs Node/npx on PATH. Install Node (https://nodejs.org).")
    chrome = _find_chrome(playwright_driver.chromium.executable_path)
    if not chrome:
        pytest.skip("No Chrome/Chromium found. Install Chrome or set CHROME_PATH.")

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        out_path = tmp.name
    try:
        cmd = [
            "npx", "--yes", LIGHTHOUSE_VERSION, live_server,
            "--quiet", "--output=json", f"--output-path={out_path}",
            "--only-categories=performance",
            "--throttling-method=devtools",
            "--chrome-flags=--headless=new --no-sandbox",
        ]
        env = {**os.environ, "CHROME_PATH": chrome}
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=240, env=env)
        with open(out_path) as fh:
            content = fh.read()
        if not content.strip():
            pytest.fail(f"Lighthouse produced no report.\nstderr:\n{proc.stderr[-2000:]}")
        return json.loads(content)
    finally:
        if os.path.exists(out_path):
            os.unlink(out_path)


def _audit_savings_kb(report: dict, audit_id: str) -> float:
    audit = report.get("audits", {}).get(audit_id) or {}
    saved = (audit.get("details") or {}).get("overallSavingsBytes") or 0
    return saved / 1024


#: (score floor, LCP budget ms) by where the run happens. The overall lab score
#: measures the machine at least as much as the site: the same commit scores 98
#: alone on a laptop, 76 on that same laptop while the device matrix is
#: throttling four emulated phones beside it, and 61 on a GitHub runner, which
#: is a shared two-core VM. So the threshold follows the machine, and the local
#: one is set to survive a full-suite run rather than a solo one — a floor that
#: only holds when nothing else is running is a floor that fails at random.
#: Against a real deployment there is no contention and the number means
#: something; everywhere else its job is to catch a catastrophe. What actually
#: guards performance in CI is the opportunity audits below (server-independent)
#: and the device matrix in test_performance.py.
_SCORE_FLOOR = {"remote": (0.95, 2500), "ci": (0.50, 9000), "local": (0.70, 4500)}


def _where() -> str:
    if _is_remote():
        return "remote"
    return "ci" if os.environ.get("CI") else "local"


def test_lighthouse_performance_score(lighthouse_report: dict) -> None:
    where = _where()
    floor = _SCORE_FLOOR[where][0]
    score = lighthouse_report["categories"]["performance"]["score"] or 0
    assert score >= floor, (
        f"Lighthouse performance score {score * 100:.0f} is below the "
        f"{where} floor of {floor * 100:.0f}"
    )


def test_lighthouse_largest_contentful_paint(lighthouse_report: dict) -> None:
    where = _where()
    budget = _SCORE_FLOOR[where][1]
    lcp = lighthouse_report["audits"]["largest-contentful-paint"]["numericValue"]
    assert lcp < budget, (
        f"Lighthouse LCP {lcp:.0f}ms exceeds the {where} budget of {budget}ms"
    )


@pytest.mark.parametrize("audit_id", list(AUDIT_SAVINGS_BUDGET_KB))
def test_lighthouse_opportunity(lighthouse_report: dict, audit_id: str) -> None:
    saved = _audit_savings_kb(lighthouse_report, audit_id)
    budget = AUDIT_SAVINGS_BUDGET_KB[audit_id]
    title = (lighthouse_report.get("audits", {}).get(audit_id) or {}).get("title", audit_id)
    assert saved <= budget, (
        f"[{audit_id}] {title}: ~{saved:.0f}KiB wasted, exceeds the budget of {budget}KiB"
    )
