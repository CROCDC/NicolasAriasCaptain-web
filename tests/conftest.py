"""Shared fixtures: a real database, an HTTP client, a live server, a browser.

The suite runs against the same database engine as production — SQLite on a
real file — with the project's own migrations applied. Between tests every table
is emptied except the migration bookkeeping, which is SQLite's answer to
TRUNCATE … RESTART IDENTITY.

Import note: assumes pytest's DEFAULT import mode with ``tests/`` NOT a package
(no ``__init__.py``) — sibling modules import by bare name.
"""

from __future__ import annotations

import os
import socket
import tempfile
from collections.abc import Iterator
from typing import Any

import pytest

import app_under_test as adapter

#: The project records applied schema changes here; it survives the wipe.
MIGRATION_TABLE = "schema_migrations"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


# ----- Database ---------------------------------------------------------------

@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    """A real database file, thrown away at the end of the session.

    A file rather than ``:memory:`` because the live server serves from another
    thread, and an in-memory SQLite database is not shared across connections.
    """
    handle, path = tempfile.mkstemp(suffix=".db", prefix="arias-test-")
    os.close(handle)
    os.remove(path)
    try:
        yield f"sqlite:///{path}"
    finally:
        for leftover in (path, f"{path}-journal", f"{path}-wal"):
            if os.path.exists(leftover):
                os.remove(leftover)


@pytest.fixture(scope="session")
def app_instance(database_url: str) -> Iterator[Any]:
    """The app under test, on the test DB, with real migrations applied."""
    app = adapter.build_app(database_url)
    adapter.apply_migrations(app, database_url)
    yield app


@pytest.fixture()
def db_clean(app_instance: Any) -> Iterator[None]:
    """Empty every table after each test, keeping the schema warm."""
    yield
    from sqlalchemy import text

    from app.factory import db

    with app_instance.app_context():
        with db.engine.begin() as conn:
            names = [row[0] for row in conn.execute(text(
                "SELECT name FROM sqlite_master WHERE type='table'"))]
            for table in names:
                if table == MIGRATION_TABLE or table.startswith("sqlite_"):
                    continue
                conn.execute(text(f'DELETE FROM "{table}"'))
            # The SQLite equivalent of RESTART IDENTITY: without it, ids keep
            # climbing across tests and an assertion on id 1 passes only once.
            if "sqlite_sequence" in names:
                conn.execute(text("DELETE FROM sqlite_sequence"))


@pytest.fixture()
def client(app_instance: Any, db_clean: None) -> Iterator[Any]:
    """HTTP test client for endpoint tests (happy + error paths)."""
    with adapter.client(app_instance) as test_client:
        yield test_client


@pytest.fixture()
def app_context(app_instance: Any, db_clean: None) -> Iterator[Any]:
    """A pushed application context, for tests that skip the HTTP layer."""
    with app_instance.app_context():
        yield app_instance


# ----- Live server + Playwright -----------------------------------------------

@pytest.fixture(scope="session")
def live_server(app_instance: Any) -> Iterator[str]:
    """Serve the real app on a free port for the browser tests.

    A real HTTP server is required: the test client serves no static assets and
    runs no JavaScript.

    ``PERF_TARGET_URL`` points the whole suite at a deployed site instead. That
    is the only way to measure what the reverse proxy and the tunnel actually
    do — compression and cache headers are theirs to add or strip, and a local
    server cannot answer for them.
    """
    external = os.environ.get("PERF_TARGET_URL")
    if external:
        yield external.rstrip("/")
        return

    server = adapter.LiveServer(app_instance, "127.0.0.1", _free_port())
    try:
        yield server.url
    finally:
        server.stop()


@pytest.fixture(scope="session")
def playwright_driver() -> Iterator[Any]:
    """The one Playwright driver the whole session shares.

    Two ``sync_playwright()`` context managers cannot be open at once: the
    second finds the first one's event loop already running and refuses with
    "use the Async API instead". The visual suite drives Firefox and the
    performance suite drives Chromium, so the driver is what they share — not
    the browser.
    """
    playwright_api = pytest.importorskip(
        "playwright.sync_api", reason="playwright is not installed")
    with playwright_api.sync_playwright() as driver:
        yield driver


@pytest.fixture(scope="session")
def browser(playwright_driver: Any) -> Iterator[Any]:
    """Chromium, for the performance suite only.

    Deliberately not ``browser_instance``: that one prefers Firefox because it
    is what the deployment image installs, and the visual baselines are its
    pixels. The performance tests cannot use it — the device matrix throttles
    CPU and network through CDP, which is Chromium-only, and the numbers are
    only comparable to Lighthouse's if they come from the same engine.

    A machine without Chromium skips instead of erroring, the way
    ``browser_instance`` already does. The deployment image ships Firefox
    alone, so this suite has to be able to say "not measurable here" rather
    than fail a deploy over a browser it was never meant to have.
    """
    try:
        instance = playwright_driver.chromium.launch(headless=True)
    except Exception as exc:  # pragma: no cover - depends on the machine
        pytest.skip("the performance suite needs Chromium ("
                    + str(exc).splitlines()[0] + "); run: make browser")

    try:
        yield instance
    finally:
        instance.close()


@pytest.fixture(scope="session")
def browser_instance(playwright_driver: Any) -> Iterator[Any]:
    """One headless browser per session, or a skip that says what is missing.

    Firefox first, because that is what the deployment image installs: the
    Playwright Chromium build crashes the renderer on Debian Trixie ARM64, and
    a suite that cannot run where the app is built is not much use. Chromium is
    accepted as a fallback so a machine that already has one browser does not
    have to download a second one to run these.

    Which one runs matters to the visual baseline and to nothing else: those
    screenshots are compared per renderer, so a browser with no committed set
    writes one and says so rather than comparing against another browser's
    pixels. GitHub Actions installs Chromium deliberately, because Chromium is
    the set this repository carries.
    """
    # An escape hatch for a machine whose browser Playwright did not install
    # itself — a CI image that ships one, say. Empty everywhere else, and then
    # Playwright's own copy is used.
    executable = os.environ.get("BROWSER_EXECUTABLE") or None

    browser = None
    failures: list[str] = []
    for name in ("firefox", "chromium"):
        try:
            browser = getattr(playwright_driver, name).launch(
                headless=True, executable_path=executable)
            break
        except Exception as exc:  # pragma: no cover - depends on the machine
            failures.append(f"{name}: {str(exc).splitlines()[0]}")

    if browser is None:
        pytest.skip("no browser for Playwright (" + "; ".join(failures)
                    + "); run: make browser")

    try:
        yield browser
    finally:
        browser.close()


@pytest.fixture()
def page(browser_instance: Any, db_clean: None) -> Iterator[Any]:
    """A fresh context and page per test — cheap, and full isolation."""
    context = browser_instance.new_context(viewport={"width": 1280, "height": 800})
    pg = context.new_page()
    try:
        yield pg
    finally:
        pg.close()
        context.close()
