"""The photographs the site expects, and which of them have arrived.

The site is built before the captain's own photographs exist. A template that
simply points an ``<img>`` at a file that is not there yet gives every visitor a
broken-image icon, and a site nobody can show is a site nobody finishes — so the
photographs are declared in one manifest, ``app/static/data/gallery.json``, and
a slot with no file behind it renders as a framed placeholder instead.

Dropping the file into ``app/static/assets/photos/`` under the name the manifest
gives it is the whole of "adding a photo": no template is touched, and the
placeholder becomes the photograph.
"""

from __future__ import annotations

import json
import os
from typing import Any

from flask import Flask

#: Where the manifest lives, relative to the static folder.
MANIFEST_PATH = os.path.join("data", "gallery.json")

#: Where the files themselves live, relative to the static folder.
PHOTO_DIR = os.path.join("assets", "photos")

#: Keys every slot in the manifest has to carry.
REQUIRED_KEYS = frozenset({"id", "kind", "file", "alt"})

#: Cached manifest, keyed by the file's modification time so an edit is picked
#: up without a restart. Whether a photograph *exists* is not cached: that is
#: the thing expected to change while the site is running.
_cache: dict[str, Any] = {"mtime": None, "slots": []}


def load_manifest(app: Flask) -> list[dict[str, Any]]:
    """Return every declared slot, validated, in manifest order."""
    path = os.path.join(app.static_folder, MANIFEST_PATH)
    mtime = os.path.getmtime(path)
    if _cache["mtime"] != mtime:
        with open(path, "r", encoding="utf-8") as handle:
            slots = json.load(handle)
        for slot in slots:
            missing = REQUIRED_KEYS - set(slot)
            if missing:
                raise ValueError(
                    f"gallery.json: slot {slot.get('id', '?')} is missing {sorted(missing)}"
                )
        _cache["mtime"] = mtime
        _cache["slots"] = slots
    return _cache["slots"]


def _resolve(app: Flask, slot: dict[str, Any]) -> dict[str, Any]:
    """A slot plus what the template needs: whether it is there, and its URL.

    The URL is built from ``static_url_path`` rather than with ``url_for``,
    because this is also called from a script and from the tests, where there is
    an application context but no request to build a URL against.
    """
    relative = os.path.join(PHOTO_DIR, slot["file"])
    available = os.path.isfile(os.path.join(app.static_folder, relative))
    resolved = dict(slot)
    resolved["available"] = available
    resolved["url"] = (
        f"{app.static_url_path}/{PHOTO_DIR.replace(os.sep, '/')}/{slot['file']}"
        if available else None
    )
    return resolved


def photos(app: Flask, kind: str) -> list[dict[str, Any]]:
    """Every slot of one kind ('hero', 'about', 'gallery', …), resolved."""
    return [_resolve(app, slot) for slot in load_manifest(app) if slot["kind"] == kind]


def photo(app: Flask, slot_id: str) -> dict[str, Any] | None:
    """One slot by id, resolved; ``None`` when the manifest does not declare it."""
    for slot in load_manifest(app):
        if slot["id"] == slot_id:
            return _resolve(app, slot)
    return None


def missing(app: Flask) -> list[str]:
    """The filenames still to be dropped into the photos directory.

    What ``make photos`` prints, so the captain can see at a glance what the
    site is still waiting for.
    """
    return [
        slot["file"] for slot in load_manifest(app)
        if not os.path.isfile(os.path.join(app.static_folder, PHOTO_DIR, slot["file"]))
    ]
