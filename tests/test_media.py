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
