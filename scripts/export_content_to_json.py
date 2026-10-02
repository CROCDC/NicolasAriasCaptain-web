#!/usr/bin/env python3
"""Copy the content panel's edits out of the SQLite file and into the JSON documents.

Run once, when this version goes out, against a copy of the production database:

    # the database, out of the arias_db volume on the Pi
    docker cp nicolas-arias-web-app:/app/instance/arias.db /tmp/arias.db

    # into a directory (CONTENT_DIR) ...
    CONTENT_DIR=/path/to/content python scripts/export_content_to_json.py /tmp/arias.db

    # ... or straight into Vercel Blob, with the production SECRET_KEY: the blob
    # names are derived from it, so a different one writes where the site never reads
    BLOB_READ_WRITE_TOKEN=... SECRET_KEY=... python scripts/export_content_to_json.py /tmp/arias.db

It refuses to overwrite documents that already hold edits; ``--force`` says that is
what you mean. The SQLite file is only read.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.json_store import JsonDocument  # noqa: E402


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()
    return row is not None


def read_texts(conn: sqlite3.Connection) -> dict[str, dict[str, str]]:
    """``site_texts`` as the texts document holds it: only the values that are set."""
    if not _table_exists(conn, "site_texts"):
        return {}
    texts: dict[str, dict[str, str]] = {}
    rows = conn.execute(
        "SELECT key, published_value, draft_value, previous_value FROM site_texts")
    for key, published, draft, previous in rows:
        entry = {name: value for name, value in (
            ("published", published), ("draft", draft), ("previous", previous))
            if value is not None}
        if entry:
            texts[key] = entry
    return texts


def read_media(conn: sqlite3.Connection) -> dict[str, list[dict[str, str]]]:
    """``site_media_versions``, oldest first per key, as the media document holds it."""
    if not _table_exists(conn, "site_media_versions"):
        return {}
    versions: dict[str, list[dict[str, str]]] = {}
    rows = conn.execute(
        "SELECT key, url, created_at FROM site_media_versions ORDER BY id")
    for key, url, created_at in rows:
        # SQLAlchemy wrote naive UTC timestamps.
        stamp = datetime.fromisoformat(str(created_at)).replace(tzinfo=timezone.utc)
        versions.setdefault(key, []).append({"url": url, "at": stamp.isoformat()})
    return versions


def export(conn: sqlite3.Connection, texts_doc: JsonDocument, media_doc: JsonDocument,
           force: bool = False) -> tuple[int, int]:
    """Write both documents. Returns (texts, photo histories) copied."""
    texts = read_texts(conn)
    media = read_media(conn)
    if not force:
        held = [doc.name for doc, field in ((texts_doc, "texts"), (media_doc, "versions"))
                if _holds(doc, field)]
        if held:
            raise SystemExit(f"already holds edits: {', '.join(held)} (use --force)")

    def put(field: str, value: Any) -> Any:
        def change(doc: dict[str, Any]) -> dict[str, Any]:
            doc[field] = value
            return doc
        return change

    texts_doc.update(put("texts", texts))
    media_doc.update(put("versions", media))
    return len(texts), len(media)


def _holds(doc: JsonDocument, field: str) -> bool:
    """True when the stored document already has something under ``field``."""
    data = doc.backend.read_fresh(doc.name).data
    return bool(data and json.loads(data).get(field))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("database", help="path to the SQLite file (arias.db)")
    parser.add_argument("--force", action="store_true",
                        help="overwrite documents that already hold edits")
    args = parser.parse_args()

    if not os.path.exists(args.database):
        raise SystemExit(f"no such file: {args.database}")

    from app import app

    text_store, media_history = app.extensions["content_stores"]
    conn = sqlite3.connect(f"file:{args.database}?mode=ro", uri=True)
    try:
        copied_texts, copied_media = export(
            conn, text_store.document, media_history.document, force=args.force)
    finally:
        conn.close()

    print(f"  Textos copiados:          {copied_texts}")
    print(f"  Historiales de fotos:     {copied_media}")
    print(f"  Destino:                  {type(text_store.document.backend).__name__}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
