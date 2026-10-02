"""The content panel's edits as JSON documents instead of database rows.

What has to hold: a visit never needs the database for copy, a process re-checks
the document only once per refresh window, a write merges onto whatever another
process saved meanwhile, a backend that stops answering does not turn edited copy
back into its defaults, and the export carries every edit out of SQLite.
"""

from __future__ import annotations

import importlib.util
import io
import json
import os
import sqlite3
import urllib.error
from typing import Any

import pytest
from sitecopy import resolver
from sitecopy.state import current_media_versions, current_store

from app.services import json_store
from app.services.json_store import (
    Fetched,
    JsonDocument,
    JsonMediaVersionStore,
    JsonTextStore,
    LocalJsonBackend,
    VercelBlobJsonBackend,
)

KEY = "portada.cta_servicios"


class Clock:
    """A monotonic clock the test moves by hand."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class CountingBackend(LocalJsonBackend):
    """A directory backend that counts reads and can be told to fail them."""

    def __init__(self, directory: str) -> None:
        super().__init__(directory)
        self.reads = 0
        self.down = False

    def read(self, name: str, tag: str | None = None) -> Fetched | None:
        self.reads += 1
        if self.down:
            raise OSError("backend unreachable")
        return super().read(name, tag)


def _publish(store: JsonTextStore, key: str, value: str) -> None:
    store.set_draft(key, value)
    store.publish([key], {})
    store.commit()


# ----- The document cache --------------------------------------------------------

def test_a_process_reads_the_document_once_per_refresh_window(tmp_path: Any) -> None:
    backend, clock = CountingBackend(str(tmp_path)), Clock()
    doc = JsonDocument(backend, "texts", refresh_seconds=30, clock=clock)

    for _ in range(50):
        doc.get()
    assert backend.reads == 1

    clock.now += 31
    doc.get()
    assert backend.reads == 2


def test_another_process_sees_a_publish_once_its_window_runs_out(tmp_path: Any) -> None:
    clock = Clock()
    writer = JsonTextStore(JsonDocument(LocalJsonBackend(str(tmp_path)), "texts", 30, clock))
    reader = JsonTextStore(JsonDocument(LocalJsonBackend(str(tmp_path)), "texts", 30, clock))
    assert reader.as_map() == {}

    _publish(writer, KEY, "Nuevo")
    assert writer.as_map() == {KEY: ("Nuevo", None)}, "the writer sees its own edit at once"
    assert reader.as_map() == {}, "the reader is still inside its window"

    clock.now += 31
    assert reader.as_map() == {KEY: ("Nuevo", None)}


def test_an_unchanged_document_is_not_downloaded_again(tmp_path: Any) -> None:
    backend = LocalJsonBackend(str(tmp_path))
    tag = backend.write("texts", b'{"format": 1}')
    assert backend.read("texts", tag) is None
    assert backend.read("texts", "something-else") is not None
    assert backend.read("missing", "absent") is None


def test_a_backend_outage_keeps_serving_the_last_copy(tmp_path: Any) -> None:
    backend, clock = CountingBackend(str(tmp_path)), Clock()
    store = JsonTextStore(JsonDocument(backend, "texts", 30, clock))
    _publish(store, KEY, "Editado")

    backend.down = True
    clock.now += 31
    assert store.as_map() == {KEY: ("Editado", None)}
    reads = backend.reads
    store.as_map()
    assert backend.reads == reads, "a failed check backs off for a whole window"


def test_a_process_that_never_read_the_document_raises_instead_of_guessing(
    tmp_path: Any,
) -> None:
    """The library answers that with the registry defaults — see the next test."""
    backend = CountingBackend(str(tmp_path))
    backend.down = True
    with pytest.raises(OSError):
        JsonTextStore(JsonDocument(backend, "texts")).as_map()


# ----- Writes ----------------------------------------------------------------------

def test_a_write_merges_onto_what_another_process_saved(tmp_path: Any) -> None:
    clock = Clock()
    first = JsonTextStore(JsonDocument(LocalJsonBackend(str(tmp_path)), "texts", 30, clock))
    second = JsonTextStore(JsonDocument(LocalJsonBackend(str(tmp_path)), "texts", 30, clock))
    first.as_map()
    second.as_map()  # both now hold the same, soon stale, copy

    _publish(first, "a.key", "uno")
    _publish(second, "b.key", "dos")

    on_disk = json.loads(open(tmp_path / "texts.json", encoding="utf-8").read())
    assert on_disk["texts"] == {"a.key": {"published": "uno"}, "b.key": {"published": "dos"}}


def test_a_rejected_submission_leaves_no_trace(tmp_path: Any) -> None:
    store = JsonTextStore(JsonDocument(LocalJsonBackend(str(tmp_path)), "texts", 0))
    store.set_draft(KEY, "a medias")
    assert store.draft_keys() == [KEY], "staged writes are visible to their own request"
    store.rollback()
    store.commit()
    assert store.draft_keys() == []
    assert not (tmp_path / "texts.json").exists()


def test_publishing_keeps_the_way_back_and_collapses_to_the_default(tmp_path: Any) -> None:
    """The write rules are the library's own — checked here end to end on disk."""
    store = JsonTextStore(JsonDocument(LocalJsonBackend(str(tmp_path)), "texts", 0))
    _publish(store, KEY, "Primero")
    _publish(store, KEY, "Segundo")
    assert store.get(KEY).previous_value == "Primero"
    assert store.previous_map() == {KEY: "Primero"}

    store.set_draft(KEY, "El de fábrica")
    store.publish([KEY], {KEY: "El de fábrica"})
    store.commit()
    row = store.get(KEY)
    assert row.published_value is None and row.previous_value == "Segundo"


def test_a_photo_history_is_recorded_once_per_change_and_capped(tmp_path: Any) -> None:
    history = JsonMediaVersionStore(JsonDocument(LocalJsonBackend(str(tmp_path)), "media", 0))
    history.record("foto.retrato", "/a.jpg")
    history.record("foto.retrato", "/a.jpg")
    history.record("foto.retrato", "/b.jpg")
    assert [v.url for v in history.versions("foto.retrato")] == ["/b.jpg", "/a.jpg"]

    for n in range(json_store.MEDIA_HISTORY_LIMIT + 10):
        history.record("foto.retrato", f"/{n}.jpg")
    kept = history.versions("foto.retrato", limit=1000)
    assert len(kept) == json_store.MEDIA_HISTORY_LIMIT
    assert kept[0].url == f"/{json_store.MEDIA_HISTORY_LIMIT + 9}.jpg"


# ----- On the real app --------------------------------------------------------------

def test_the_app_keeps_the_panel_out_of_the_database(app_instance: Any) -> None:
    with app_instance.app_context():
        assert isinstance(current_store(), JsonTextStore)
        assert isinstance(current_media_versions(), JsonMediaVersionStore)


def test_a_published_edit_reaches_the_page_and_the_file(
    client: Any, app_instance: Any,
) -> None:
    with app_instance.test_request_context():
        store = current_store()
        store.set_draft(KEY, "Patrón de prueba")
        store.publish([KEY], {})
        resolver.save()

    assert "Patrón de prueba" in client.get("/").get_data(as_text=True)
    path = os.path.join(os.environ["CONTENT_DIR"], "texts.json")
    assert json.load(open(path, encoding="utf-8"))["texts"][KEY] == {
        "published": "Patrón de prueba"}


def test_an_unreadable_document_renders_the_defaults(
    client: Any, app_instance: Any,
) -> None:
    os.makedirs(os.environ["CONTENT_DIR"], exist_ok=True)
    with open(os.path.join(os.environ["CONTENT_DIR"], "texts.json"), "w") as handle:
        handle.write("{ no es json")
    response = client.get("/")
    assert response.status_code == 200


# ----- Vercel Blob -----------------------------------------------------------------

TOKEN = "vercel_blob_rw_AbC123xyz_s3cr3tpart"


class FakeResponse(io.BytesIO):
    def __init__(self, body: bytes, headers: dict[str, str] | None = None) -> None:
        super().__init__(body)
        self.headers = headers or {}

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


def test_blob_names_come_from_the_secret_and_never_contain_it() -> None:
    one = VercelBlobJsonBackend(TOKEN, secret="clave-uno")
    two = VercelBlobJsonBackend(TOKEN, secret="clave-dos")
    assert one.base_url == "https://abc123xyz.public.blob.vercel-storage.com"
    assert one.pathname("texts") != two.pathname("texts")
    assert "clave-uno" not in one.pathname("texts")
    assert TOKEN not in one.pathname("texts")


def test_blob_writes_overwrite_in_place_and_reads_are_conditional(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = VercelBlobJsonBackend(TOKEN, secret="clave")
    sent: list[Any] = []

    def fake_urlopen(req: Any, timeout: float) -> FakeResponse:
        sent.append(req)
        if req.get_method() == "PUT":
            url = f"{backend.base_url}/{backend.pathname('texts')}"
            return FakeResponse(json.dumps({"url": url}).encode())
        if req.get_header("If-none-match") == '"v1"':
            raise urllib.error.HTTPError(req.full_url, 304, "Not Modified", {}, None)
        return FakeResponse(b'{"format": 1}', {"ETag": '"v1"'})

    monkeypatch.setattr(json_store.urllib.request, "urlopen", fake_urlopen)

    backend.write("texts", b'{"format": 1}')
    put = sent[-1]
    assert put.get_header("X-allow-overwrite") == "1"
    assert put.get_header("X-add-random-suffix") == "0"
    assert backend.pathname("texts") in put.full_url

    assert backend.read("texts").tag == '"v1"'
    assert backend.read("texts", '"v1"') is None

    backend.read_fresh("texts")
    assert "?fresh=" in sent[-1].full_url, "a write merges onto the origin's copy"


def test_a_missing_blob_is_an_empty_document(monkeypatch: pytest.MonkeyPatch) -> None:
    def not_found(req: Any, timeout: float) -> Any:
        raise urllib.error.HTTPError(req.full_url, 404, "Not Found", {}, None)

    monkeypatch.setattr(json_store.urllib.request, "urlopen", not_found)
    backend = VercelBlobJsonBackend(TOKEN, secret="clave")
    assert JsonDocument(backend, "texts").get() == {"format": 1}


# ----- The export out of SQLite -----------------------------------------------------

def _export_module() -> Any:
    path = os.path.join(os.path.dirname(__file__), "..", "scripts",
                        "export_content_to_json.py")
    spec = importlib.util.spec_from_file_location("export_content_to_json", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _legacy_database(path: str) -> sqlite3.Connection:
    """The two tables flask-sitecopy kept in arias.db before this change."""
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE site_texts (key TEXT PRIMARY KEY, published_value TEXT,
                                 draft_value TEXT, previous_value TEXT, updated_at TEXT);
        CREATE TABLE site_media_versions (id INTEGER PRIMARY KEY, key TEXT, url TEXT,
                                          created_at TEXT);
        INSERT INTO site_texts VALUES ('portada.cta_servicios', 'Vivo', NULL, 'Antes', NULL);
        INSERT INTO site_texts VALUES ('contact.title', NULL, 'Borrador', NULL, NULL);
        INSERT INTO site_media_versions VALUES (1, 'foto.retrato', '/a.jpg',
                                                '2026-09-01 10:00:00.000000');
        INSERT INTO site_media_versions VALUES (2, 'foto.retrato', '/b.jpg',
                                                '2026-09-02 10:00:00.000000');
    """)
    return conn


def test_the_export_carries_every_edit_out_of_sqlite(tmp_path: Any) -> None:
    export = _export_module()
    conn = _legacy_database(str(tmp_path / "arias.db"))
    backend = LocalJsonBackend(str(tmp_path / "content"))
    texts = JsonTextStore(JsonDocument(backend, "texts", 0))
    media = JsonMediaVersionStore(JsonDocument(backend, "media", 0))

    assert export.export(conn, texts.document, media.document) == (2, 1)
    assert texts.as_map() == {"portada.cta_servicios": ("Vivo", None),
                              "contact.title": (None, "Borrador")}
    assert texts.previous_map() == {"portada.cta_servicios": "Antes"}
    assert [v.url for v in media.versions("foto.retrato")] == ["/b.jpg", "/a.jpg"]

    with pytest.raises(SystemExit, match="already holds edits"):
        export.export(conn, texts.document, media.document)
    assert export.export(conn, texts.document, media.document, force=True) == (2, 1)
