"""Booting the app the way gunicorn does: several workers at once, one database."""

from __future__ import annotations

import multiprocessing
import os
import sys
import tempfile

#: gunicorn runs two workers in production; more makes the collision likelier.
WORKERS = 6
ROUNDS = 5


def _boot(database_url: str) -> None:
    """What a gunicorn worker does for ``run:app``: importing the package builds it."""
    os.environ["DATABASE_URL"] = database_url
    os.environ["SECRET_KEY"] = "test-secret-key"
    try:
        import app  # noqa: F401
    except Exception as error:  # noqa: BLE001 — reported through the exit code
        print(f"{type(error).__name__}: {error}".splitlines()[0], file=sys.stderr)
        sys.exit(1)


def test_workers_booting_together_on_a_fresh_database_all_come_up() -> None:
    """Every worker creates the missing tables at once, and none of them dies.

    A deploy that brought a new table crashed the loser of that race on "table
    already exists", and gunicorn took the whole container down with it.
    """
    context = multiprocessing.get_context("spawn")
    exit_codes: list[int | None] = []
    for _ in range(ROUNDS):
        with tempfile.TemporaryDirectory() as directory:
            database_url = f"sqlite:///{os.path.join(directory, 'arias.db')}"
            workers = [context.Process(target=_boot, args=(database_url,))
                       for _ in range(WORKERS)]
            for worker in workers:
                worker.start()
            for worker in workers:
                worker.join(timeout=60)
                if worker.is_alive():
                    worker.kill()
                exit_codes.append(worker.exitcode)
    assert exit_codes == [0] * (WORKERS * ROUNDS)
