"""The photo manifest, and the placeholder that stands in for a missing file.

The photographs have arrived, so "the file is not there yet" is no longer the
resting state of the site — it is the state a slot falls back to when a file is
renamed, lost or newly declared. These tests stage that state instead of
assuming it, and keep a manifest typo from reaching a page as a broken image.
"""

from __future__ import annotations

import os
from typing import Any, Iterator

import pytest

from app.services import media

#: A 1x1 GIF: the smallest thing that is unambiguously a file on disk.
ONE_PIXEL_GIF = (
    b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!"
    b"\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00"
    b"\x00\x02\x02D\x01\x00;"
)

#: The slot these tests borrow. Any one would do; this one is on every page.
SUBJECT = "retrato"


def _subject(app: Any) -> tuple[dict[str, Any], str]:
    slot = next(s for s in media.load_manifest(app) if s["id"] == SUBJECT)
    return slot, os.path.join(app.static_folder, media.PHOTO_DIR, slot["file"])


@pytest.fixture()
def photo_file(app_instance: Any) -> Iterator[dict[str, Any]]:
    """Put a file behind the subject slot, and restore what was there before.

    Restoring rather than deleting: the photographs live in the repository now,
    and a fixture that cleaned up with ``os.remove`` cost a real one per run.
    """
    slot, path = _subject(app_instance)
    kept = open(path, "rb").read() if os.path.exists(path) else None
    with open(path, "wb") as handle:
        handle.write(ONE_PIXEL_GIF)
    try:
        yield slot
    finally:
        if kept is None:
            os.remove(path)
        else:
            with open(path, "wb") as handle:
                handle.write(kept)


@pytest.fixture()
def photo_gone(app_instance: Any) -> Iterator[dict[str, Any]]:
    """Take the subject's file off disk for one test, then put it back."""
    slot, path = _subject(app_instance)
    kept = open(path, "rb").read() if os.path.exists(path) else None
    if kept is not None:
        os.remove(path)
    try:
        yield slot
    finally:
        if kept is not None:
            with open(path, "wb") as handle:
                handle.write(kept)


def test_every_slot_declares_what_a_template_needs(app_context: Any) -> None:
    for slot in media.load_manifest(app_context):
        assert media.REQUIRED_KEYS <= set(slot), slot
        assert slot["alt"].strip(), f"{slot['id']} has no alt text"


def test_slot_ids_are_unique(app_context: Any) -> None:
    ids = [slot["id"] for slot in media.load_manifest(app_context)]
    assert len(ids) == len(set(ids))


def test_a_slot_with_no_file_is_reported_as_missing(
    app_context: Any, photo_gone: dict[str, Any]
) -> None:
    slot = media.photo(app_context, photo_gone["id"])
    assert slot is not None
    assert slot["available"] is False
    assert slot["url"] is None
    assert slot["file"] in media.missing(app_context)


def test_a_slot_whose_file_arrived_is_served(
    app_context: Any, photo_file: dict[str, Any]
) -> None:
    slot = media.photo(app_context, photo_file["id"])
    assert slot["available"] is True
    assert slot["url"].startswith("/static/assets/photos/")
    assert slot["file"] not in media.missing(app_context)


def test_photos_filters_by_kind(app_context: Any) -> None:
    gallery = media.photos(app_context, "gallery")
    assert gallery, "the gallery declares no photographs"
    assert {slot["kind"] for slot in gallery} == {"gallery"}


def test_an_unknown_slot_is_none_rather_than_an_error(app_context: Any) -> None:
    assert media.photo(app_context, "no-such-slot") is None


def test_the_page_renders_a_placeholder_and_not_a_broken_image(
    client: Any, photo_gone: dict[str, Any]
) -> None:
    body = client.get("/").get_data(as_text=True)
    assert "shot-empty" in body
    # The box carries the description of the photograph that belongs there —
    # which is that photograph's alt text.
    assert photo_gone["alt"] in body
    # The markup does name the missing file, in a data attribute for whoever has
    # to supply it — what must not appear is a src pointing at it.
    assert f'src="/static/assets/photos/{photo_gone["file"]}"' not in body


def test_the_page_renders_the_photograph_once_it_arrives(
    client: Any, photo_file: dict[str, Any]
) -> None:
    body = client.get("/").get_data(as_text=True)
    assert f"/static/assets/photos/{photo_file['file']}" in body


# ----- Photographs replaced from the content panel ----------------------------

def _publish_override(app: Any, slot_id: str, url: str) -> None:
    """What the panel does on "publish": a draft for the key, then made live."""
    from sitecopy import resolver
    from sitecopy.state import current_store

    with app.test_request_context():
        store = current_store()
        store.set_draft(f"foto.{slot_id}", url)
        store.publish([f"foto.{slot_id}"], {})
        resolver.save()


def test_uploads_land_on_the_volume_and_publishing_can_record_them(
    app_instance: Any,
) -> None:
    """The upload store is the one docker-compose keeps across deploys.

    It used to be passed as ``media_store=`` — sitecopy's *version history* —
    so uploads fell back to static/sitecopy-uploads, inside the container, and
    were gone after the next deploy; and publishing a photo 500'd, because the
    history store it was handed has no ``record``.
    """
    from sitecopy.state import current_file_store, current_media_versions

    with app_instance.app_context():
        files = current_file_store()
        versions = current_media_versions()
    assert files.directory == os.path.join(
        app_instance.static_folder, "assets", "subidas")
    assert files.base_url == "/static/assets/subidas"
    assert callable(getattr(versions, "record", None))


def test_a_replaced_photo_whose_upload_is_gone_falls_back_to_the_shipped_one(
    client: Any, app_instance: Any
) -> None:
    """A lost upload undoes the replacement instead of greying out the slot."""
    slot, _ = _subject(app_instance)
    _publish_override(app_instance, SUBJECT,
                      "/static/assets/subidas/0000000000000000.jpg")
    body = client.get("/").get_data(as_text=True)
    assert "0000000000000000.jpg" not in body
    assert f'src="/static/assets/photos/{slot["file"]}"' in body
    assert f'data-file="{slot["file"]}"' not in body


def test_a_replaced_photo_whose_upload_is_there_is_served(
    client: Any, app_instance: Any
) -> None:
    directory = os.path.join(app_instance.static_folder, "assets", "subidas")
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, "test-subida.gif")
    with open(path, "wb") as handle:
        handle.write(ONE_PIXEL_GIF)
    try:
        _publish_override(app_instance, SUBJECT,
                          "/static/assets/subidas/test-subida.gif")
        body = client.get("/").get_data(as_text=True)
        assert 'src="/static/assets/subidas/test-subida.gif"' in body
    finally:
        os.remove(path)
