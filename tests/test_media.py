"""The photo manifest, and the placeholder that stands in for a missing file.

The site is being built before the photographs exist, so "the file is not there
yet" is the normal case and has to render as something finished. These are the
tests that keep it that way — and that keep a manifest typo from reaching a
page as a broken image.
"""

from __future__ import annotations

import os
from typing import Any, Iterator

import pytest

from app.services import media


@pytest.fixture()
def photo_file(app_instance: Any) -> Iterator[str]:
    """Put a real file behind the 'retrato' slot, and take it away after."""
    slot = next(s for s in media.load_manifest(app_instance) if s["id"] == "retrato")
    path = os.path.join(app_instance.static_folder, media.PHOTO_DIR, slot["file"])
    # A 1x1 GIF: the smallest thing that is unambiguously a file on disk.
    with open(path, "wb") as handle:
        handle.write(
            b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!"
            b"\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00"
            b"\x00\x02\x02D\x01\x00;"
        )
    try:
        yield path
    finally:
        os.remove(path)


def test_every_slot_declares_what_a_template_needs(app_context: Any) -> None:
    for slot in media.load_manifest(app_context):
        assert media.REQUIRED_KEYS <= set(slot), slot
        assert slot["alt"].strip(), f"{slot['id']} has no alt text"


def test_slot_ids_are_unique(app_context: Any) -> None:
    ids = [slot["id"] for slot in media.load_manifest(app_context)]
    assert len(ids) == len(set(ids))


def test_a_slot_with_no_file_is_reported_as_missing(app_context: Any) -> None:
    slot = media.photo(app_context, "galeria-01")
    assert slot is not None
    assert slot["available"] is False
    assert slot["url"] is None
    assert slot["file"] in media.missing(app_context)


def test_a_slot_whose_file_arrived_is_served(app_context: Any, photo_file: str) -> None:
    slot = media.photo(app_context, "retrato")
    assert slot["available"] is True
    assert slot["url"].startswith("/static/assets/photos/")
    assert slot["file"] not in media.missing(app_context)


def test_photos_filters_by_kind(app_context: Any) -> None:
    gallery = media.photos(app_context, "gallery")
    assert gallery, "the gallery declares no photographs"
    assert {slot["kind"] for slot in gallery} == {"gallery"}


def test_an_unknown_slot_is_none_rather_than_an_error(app_context: Any) -> None:
    assert media.photo(app_context, "no-such-slot") is None


def test_the_page_renders_a_placeholder_and_not_a_broken_image(client: Any) -> None:
    body = client.get("/").get_data(as_text=True)
    assert "photo-pending" in body
    assert "Foto en camino" in body
    # Nothing points at a file that is not there. (The markup does name the
    # missing files, in an HTML comment for whoever has to supply them — what
    # must not appear is a src.)
    assert 'src="/static/assets/photos/' not in body


def test_the_page_renders_the_photograph_once_it_arrives(
    client: Any, photo_file: str
) -> None:
    body = client.get("/").get_data(as_text=True)
    assert "/static/assets/photos/retrato.webp" in body
