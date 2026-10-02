"""The content panel's overrides, kept in a JSON document instead of a database.

What the panel stores is small (a row per edited string), read on every page and
written a handful of times a month. A database is the expensive way to hold that:
on a hosted Postgres every page view is a query, and every query keeps a billed
compute awake for minutes. Here the whole thing is one JSON file that each process
keeps in memory and re-checks at most every ``refresh_seconds`` — a conditional
read that is answered "not modified" almost every time. A visit never waits on a
database, and an edit reaches every process within that window.

Two documents, so the hot one stays small:

    texts.json   every override: published, draft and previous value per key
    media.json   the history of URLs each photo field has pointed at

Where the bytes live is a ``JsonBackend``: a directory on disk (the Docker volume
today, a plain folder in development and tests) or Vercel Blob, picked by
``backend_from_env``.

Writes are read-modify-write. The panel's edits are staged per request (the
library's all-or-nothing form handling rolls them back on a rejected submission)
and, on commit, replayed against a FRESH read of the document under the backend's
lock — so an edit saved by another process a second ago is merged, not overwritten.
"""

from __future__ import annotations

import fcntl
import hashlib
import hmac
import json
import logging
import os
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from flask import Flask, g, has_app_context, has_request_context, request
from sitecopy.media import MediaVersion, MediaVersionStore
from sitecopy.storage import MemoryStore, TextRow, TextStore

log = logging.getLogger(__name__)

TEXTS = "texts"
MEDIA = "media"

#: Bumped only if the shape of a document ever changes incompatibly.
FORMAT = 1

#: How old a process's copy may get before it asks the backend again.
DEFAULT_REFRESH_SECONDS = 30.0

#: Past URLs kept per photo. The gallery shows 24; the rest is headroom, and the
#: cap is what keeps media.json from growing for as long as the site lives.
MEDIA_HISTORY_LIMIT = 50


# ----- Backends -----------------------------------------------------------------

@dataclass(frozen=True)
class Fetched:
    """One read of a document. ``data`` is None when the document does not exist."""

    data: bytes | None
    tag: str | None


class JsonBackend(ABC):
    """Somewhere to keep a few named JSON documents."""

    @abstractmethod
    def read(self, name: str, tag: str | None = None) -> Fetched | None:
        """The document as it is now, or None when it has not changed since ``tag``."""

    @abstractmethod
    def read_fresh(self, name: str) -> Fetched:
        """The document, bypassing every cache: what a write is merged onto."""

    @abstractmethod
    def write(self, name: str, data: bytes) -> str | None:
        """Replace the document. Returns its new tag when the backend knows it."""

    @contextmanager
    def lock(self, name: str) -> Iterator[None]:
        """Held around read-modify-write. A no-op where the backend cannot lock."""
        yield


class LocalJsonBackend(JsonBackend):
    """Documents as files in a directory, safe across the gunicorn workers."""

    def __init__(self, directory: str) -> None:
        self.directory = directory

    def path(self, name: str) -> str:
        return os.path.join(self.directory, f"{name}.json")

    def read(self, name: str, tag: str | None = None) -> Fetched | None:
        try:
            info = os.stat(self.path(name))
        except FileNotFoundError:
            return None if tag == "absent" else Fetched(None, "absent")
        current = f"{info.st_mtime_ns}-{info.st_size}"
        if current == tag:
            return None
        return self.read_fresh(name)

    def read_fresh(self, name: str) -> Fetched:
        path = self.path(name)
        try:
            with open(path, "rb") as handle:
                info = os.fstat(handle.fileno())
                return Fetched(handle.read(), f"{info.st_mtime_ns}-{info.st_size}")
        except FileNotFoundError:
            return Fetched(None, "absent")

    def write(self, name: str, data: bytes) -> str | None:
        os.makedirs(self.directory, exist_ok=True)
        # Write beside and rename over: a reader never sees half a document.
        handle, temp = tempfile.mkstemp(dir=self.directory, prefix=f".{name}-")
        try:
            with os.fdopen(handle, "wb") as out:
                out.write(data)
            os.replace(temp, self.path(name))
        except BaseException:
            if os.path.exists(temp):
                os.remove(temp)
            raise
        info = os.stat(self.path(name))
        return f"{info.st_mtime_ns}-{info.st_size}"

    @contextmanager
    def lock(self, name: str) -> Iterator[None]:
        os.makedirs(self.directory, exist_ok=True)
        with open(os.path.join(self.directory, f".{name}.lock"), "a") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)


class VercelBlobJsonBackend(JsonBackend):
    """Documents as public blobs in Vercel Blob, under names nobody can guess.

    The blobs are public — Blob's CDN is what makes a read cheap — so what keeps
    unpublished drafts private is the pathname: it carries an HMAC of the app's
    SECRET_KEY, is never rendered into a page and cannot be derived without the
    secret. Rotating SECRET_KEY therefore moves the documents: copy them over
    (scripts/export_content_to_json.py) before rotating.

    Blob has no lock. Two writes landing in the same instant, from two processes,
    would keep the second; with one person editing the site that does not happen,
    and every write is still merged onto a fresh read rather than a cached one.
    """

    API_URL = "https://blob.vercel-storage.com"
    # Blob's HTTP API is versioned by header; 10 is what the official SDKs send.
    API_VERSION = "10"
    # Blob's floor. Readers poll with a conditional GET, so this only bounds how
    # long the CDN may answer with the previous copy after a write.
    CACHE_MAX_AGE = "60"

    def __init__(self, token: str, secret: str, public_base_url: str | None = None,
                 timeout: float = 10.0) -> None:
        if not token:
            raise ValueError("VercelBlobJsonBackend needs BLOB_READ_WRITE_TOKEN")
        if not secret:
            raise ValueError("VercelBlobJsonBackend needs a SECRET_KEY to name its blobs")
        self.token = token
        self.timeout = timeout
        digest = hmac.new(secret.encode(), b"sitecopy-json", hashlib.sha256).hexdigest()
        self.prefix = f"sitecopy/{digest[:32]}"
        # The public host is the store id the token carries
        # (vercel_blob_rw_<storeId>_<secret>). BLOB_PUBLIC_BASE_URL overrides it if
        # that ever stops holding; write() warns when the two disagree.
        self.base_url = (public_base_url or self._base_url_from_token(token)).rstrip("/")

    @staticmethod
    def _base_url_from_token(token: str) -> str:
        parts = token.split("_")
        if len(parts) < 5 or parts[:3] != ["vercel", "blob", "rw"]:
            raise ValueError("unrecognised BLOB_READ_WRITE_TOKEN; set BLOB_PUBLIC_BASE_URL")
        return f"https://{parts[3].lower()}.public.blob.vercel-storage.com"

    def pathname(self, name: str) -> str:
        return f"{self.prefix}/{name}.json"

    def _get(self, url: str, headers: dict[str, str]) -> Fetched | None:
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                return Fetched(response.read(), response.headers.get("ETag"))
        except urllib.error.HTTPError as exc:
            if exc.code == 304:
                return None
            if exc.code == 404:
                return Fetched(None, "absent")
            raise

    def read(self, name: str, tag: str | None = None) -> Fetched | None:
        headers = {}
        if tag and tag != "absent":
            headers["If-None-Match"] = tag
        fetched = self._get(f"{self.base_url}/{self.pathname(name)}", headers)
        if fetched is not None and fetched.data is None and tag == "absent":
            return None
        return fetched

    def read_fresh(self, name: str) -> Fetched:
        # A query string nobody has asked for before is a CDN miss: the origin's
        # copy, not one cached before somebody else's write.
        url = f"{self.base_url}/{self.pathname(name)}?fresh={uuid.uuid4().hex}"
        fetched = self._get(url, {"Cache-Control": "no-cache"})
        assert fetched is not None  # no If-None-Match was sent
        return fetched

    def write(self, name: str, data: bytes) -> str | None:
        pathname = self.pathname(name)
        req = urllib.request.Request(
            f"{self.API_URL}/?pathname={urllib.parse.quote(pathname)}",
            data=data,
            method="PUT",
            headers={
                "access": "public",
                "authorization": f"Bearer {self.token}",
                "x-api-version": self.API_VERSION,
                "x-content-type": "application/json",
                "x-cache-control-max-age": self.CACHE_MAX_AGE,
                "x-add-random-suffix": "0",
                "x-allow-overwrite": "1",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                payload = json.load(response)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:500]
            raise RuntimeError(f"Vercel Blob write failed ({exc.code}): {detail}") from exc
        url = str(payload.get("url") or "")
        expected = f"{self.base_url}/{pathname}"
        if url and url != expected:
            log.warning("Blob stored %s at %s, but reads go to %s: set BLOB_PUBLIC_BASE_URL",
                        name, url, expected)
        return None


def backend_from_env(app: Flask) -> JsonBackend:
    """Vercel Blob when the project has a Blob store attached, a directory otherwise.

    The directory defaults to the instance folder — the arias_db volume in Docker,
    the same place the SQLite file lives.
    """
    token = os.getenv("BLOB_READ_WRITE_TOKEN")
    if token:
        return VercelBlobJsonBackend(
            token,
            secret=app.config["SECRET_KEY"],
            public_base_url=os.getenv("BLOB_PUBLIC_BASE_URL") or None,
        )
    return LocalJsonBackend(os.getenv("CONTENT_DIR") or app.instance_path)


# ----- One document, cached per process -------------------------------------------

class JsonDocument:
    """A process's copy of one document, re-checked at most every ``refresh_seconds``.

    A failed check keeps serving the last copy that was read: a backend hiccup must
    not turn every edited string back into its default. Only a process that has
    never read the document successfully raises — and the library answers that with
    the defaults, which is the best a cold process can do.
    """

    def __init__(self, backend: JsonBackend, name: str,
                 refresh_seconds: float = DEFAULT_REFRESH_SECONDS,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.backend = backend
        self.name = name
        self.refresh_seconds = refresh_seconds
        self.clock = clock
        self._mutex = threading.Lock()
        self._value: dict[str, Any] | None = None
        self._tag: str | None = None
        self._checked_at = 0.0

    def get(self) -> dict[str, Any]:
        with self._mutex:
            now = self.clock()
            if self._value is not None and now - self._checked_at < self.refresh_seconds:
                return self._value
            try:
                fetched = self.backend.read(self.name, self._tag)
            except Exception:
                if self._value is None:
                    raise
                log.warning("could not re-check %s; serving the copy from before",
                            self.name, exc_info=True)
                # Back off for one interval instead of retrying on every request.
                self._checked_at = now
                return self._value
            if fetched is not None:
                self._value = _decode(fetched.data)
                self._tag = fetched.tag
            self._checked_at = now
            assert self._value is not None
            return self._value

    def update(self, change: Callable[[dict[str, Any]], dict[str, Any]]) -> dict[str, Any]:
        """Apply ``change`` to the freshest copy and write the result back."""
        with self.backend.lock(self.name):
            fetched = self.backend.read_fresh(self.name)
            value = change(_decode(fetched.data))
            value["format"] = FORMAT
            tag = self.backend.write(self.name, _encode(value))
        with self._mutex:
            self._value = value
            # Without a tag the next check downloads the document once more, which
            # is also what tells this process if somebody else wrote after it.
            self._tag = tag
            self._checked_at = self.clock()
        return value

    def forget(self) -> None:
        """Drop this process's copy, so the next read goes to the backend."""
        with self._mutex:
            self._value = None
            self._tag = None
            self._checked_at = 0.0


def _decode(data: bytes | None) -> dict[str, Any]:
    if not data:
        return {"format": FORMAT}
    value = json.loads(data.decode("utf-8"))
    if not isinstance(value, dict) or value.get("format", FORMAT) > FORMAT:
        raise ValueError("document written by a newer version of this code")
    return value


def _encode(value: dict[str, Any]) -> bytes:
    return json.dumps(value, ensure_ascii=False, indent=1, sort_keys=True).encode("utf-8")


# ----- Texts ----------------------------------------------------------------------

def _rows_from(doc: dict[str, Any]) -> dict[str, TextRow]:
    return {
        key: TextRow(key, entry.get("published"), entry.get("draft"), entry.get("previous"))
        for key, entry in doc.get("texts", {}).items()
    }


def _texts_from(rows: dict[str, TextRow]) -> dict[str, dict[str, str]]:
    texts = {}
    for key, row in rows.items():
        entry = {
            name: value
            for name, value in (("published", row.published_value),
                                ("draft", row.draft_value),
                                ("previous", row.previous_value))
            if value is not None
        }
        if entry:
            texts[key] = entry
    return texts


@dataclass
class _Staged:
    """One request's pending writes: what they look like, and how to replay them."""

    view: MemoryStore
    ops: list[tuple[str, tuple[Any, ...]]]


class JsonTextStore(TextStore):
    """sitecopy's ``TextStore`` on a JSON document.

    The write semantics — a draft equal to the default collapses on publish,
    previous_value as the way back, an emptied row disappears — are the library's
    own ``MemoryStore``: this class stages a request's writes on one and replays
    them onto another at commit, so there is no second copy of those rules to drift.
    """

    def __init__(self, document: JsonDocument) -> None:
        self.document = document
        self._attr = f"_json_text_store_{id(self)}"

    # --- staging, per request ---

    def _holder(self) -> Any:
        if has_request_context():
            return request
        if has_app_context():
            return g
        return self

    def _staged(self) -> _Staged | None:
        return getattr(self._holder(), self._attr, None)

    def _stage(self) -> _Staged:
        staged = self._staged()
        if staged is None:
            view = MemoryStore()
            view.rows = _rows_from(self.document.get())
            staged = _Staged(view, [])
            setattr(self._holder(), self._attr, staged)
        return staged

    def _write(self, op: str, *args: Any) -> Any:
        staged = self._stage()
        staged.ops.append((op, args))
        return getattr(staged.view, op)(*args)

    def _view(self) -> MemoryStore:
        """What this request sees: its own staged writes, or the shared copy."""
        staged = self._staged()
        if staged is not None:
            return staged.view
        view = MemoryStore()
        view.rows = _rows_from(self.document.get())
        return view

    # --- reads ---

    def as_map(self) -> dict[str, tuple[str | None, str | None]]:
        # The hot path — once per page view — so it reads the document directly
        # instead of building rows it would throw away.
        staged = self._staged()
        if staged is not None:
            return staged.view.as_map()
        return {
            key: (entry.get("published"), entry.get("draft"))
            for key, entry in self.document.get().get("texts", {}).items()
        }

    def previous_map(self) -> dict[str, str]:
        return self._view().previous_map()

    def draft_keys(self) -> list[str]:
        return self._view().draft_keys()

    def get(self, key: str) -> TextRow | None:
        return self._view().get(key)

    # --- writes, staged until commit ---

    def set_draft(self, key: str, value: str | None) -> None:
        self._write("set_draft", key, value)

    def set_published(self, key: str, value: str | None) -> None:
        self._write("set_published", key, value)

    def delete(self, key: str) -> bool:
        return bool(self._write("delete", key))

    def publish(self, keys: list[str], defaults: dict[str, str]) -> int:
        return int(self._write("publish", list(keys), dict(defaults)))

    def discard_drafts(self, keys: list[str]) -> int:
        return int(self._write("discard_drafts", list(keys)))

    def commit(self) -> None:
        staged = self._staged()
        if staged is None:
            return
        self._clear()
        if not staged.ops:
            return

        def replay(doc: dict[str, Any]) -> dict[str, Any]:
            fresh = MemoryStore()
            fresh.rows = _rows_from(doc)
            for op, args in staged.ops:
                getattr(fresh, op)(*args)
            fresh.commit()
            doc["texts"] = _texts_from(fresh.rows)
            return doc

        self.document.update(replay)

    def rollback(self) -> None:
        self._clear()

    def _clear(self) -> None:
        holder = self._holder()
        if hasattr(holder, self._attr):
            delattr(holder, self._attr)


# ----- Photo history --------------------------------------------------------------

class JsonMediaVersionStore(MediaVersionStore):
    """sitecopy's photo history on a JSON document. Written as it is recorded."""

    def __init__(self, document: JsonDocument) -> None:
        self.document = document

    def record(self, key: str, url: str) -> None:
        if not url:
            return
        history = self.document.get().get("versions", {}).get(key, [])
        if history and history[-1]["url"] == url:
            return  # the newest entry already says this

        def append(doc: dict[str, Any]) -> dict[str, Any]:
            versions = doc.setdefault("versions", {})
            bucket = versions.setdefault(key, [])
            if bucket and bucket[-1]["url"] == url:
                return doc
            bucket.append({"url": url, "at": datetime.now(timezone.utc).isoformat()})
            del bucket[:-MEDIA_HISTORY_LIMIT]
            return doc

        self.document.update(append)

    def versions(self, key: str, limit: int = 24) -> list[MediaVersion]:
        bucket = self.document.get().get("versions", {}).get(key, [])
        return [
            MediaVersion(key, entry["url"], datetime.fromisoformat(entry["at"]))
            for entry in reversed(bucket)
        ][:limit]


def stores_from_env(app: Flask) -> tuple[JsonTextStore, JsonMediaVersionStore]:
    """The two stores the content panel is mounted with, on the configured backend."""
    backend = backend_from_env(app)
    refresh = float(os.getenv("CONTENT_REFRESH_SECONDS", DEFAULT_REFRESH_SECONDS))
    return (
        JsonTextStore(JsonDocument(backend, TEXTS, refresh)),
        JsonMediaVersionStore(JsonDocument(backend, MEDIA, refresh)),
    )
