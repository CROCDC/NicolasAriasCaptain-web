"""The Flask adapter: everything the fixtures need to know about this app.

Kept apart from conftest.py so the fixtures stay framework-agnostic. Two
deliberate choices, both so the suite runs against what production runs:

* **SQLite on a real file, not a Postgres container.** Production is
  ``sqlite:////app/instance/arias.db``. Testing against an engine the app never
  touches would pass on behaviour that does not exist and miss behaviour that
  does.
* **The project's own migrations.** Schema changes are recorded in
  ``app.factory._MIGRATIONS`` and applied at boot, so building the app *is*
  applying them, and every run exercises them.
"""

from __future__ import annotations

import os
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from werkzeug.serving import make_server


def build_app(database_url: str) -> Any:
    """The app under test, pointed at the test database.

    ``create_app`` reads its configuration from the environment, so the
    environment is what gets pointed at the test database.
    """
    os.environ["DATABASE_URL"] = database_url
    os.environ["SECRET_KEY"] = "test-secret-key"

    from app import create_app

    app = create_app()
    app.config["TESTING"] = True
    return app


def apply_migrations(app: Any, database_url: str) -> None:
    """Already done: ``create_app`` runs the recorded migrations at boot.

    Kept so the adapter honours the contract, and so the assertion below fails
    loudly if that ever stops being true.
    """
    from sqlalchemy import inspect

    from app.factory import db

    with app.app_context():
        tables = set(inspect(db.engine).get_table_names())
    missing = {"schema_migrations", "contact_messages"} - tables
    assert not missing, f"migrations did not produce {missing}"


@contextmanager
def client(app: Any) -> Iterator[Any]:
    """HTTP test client for endpoint tests (happy + error paths)."""
    with app.test_client() as test_client:
        yield test_client


class LiveServer:
    """Real WSGI server in a background thread (threaded → parallel assets)."""

    def __init__(self, app: Any, host: str, port: int) -> None:
        self._server = make_server(host, port, app, threaded=True)
        self._thread = threading.Thread(target=self._server.serve_forever,
                                        daemon=True)
        self._thread.start()
        self.url = f"http://{host}:{port}"

    def stop(self) -> None:
        self._server.shutdown()
        self._thread.join(timeout=2)
