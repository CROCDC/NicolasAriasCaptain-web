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

#: The narrower widths ``scripts/gen_responsive_images.py`` writes. Keep the two
#: in step: this list is what the templates offer, that script is what exists.
VARIANT_WIDTHS = (400, 700)

#: Cached manifest, keyed by the file's modification time so an edit is picked
#: up without a restart. Whether a photograph *exists* is not cached: that is
#: the thing expected to change while the site is running.
_cache: dict[str, Any] = {"mtime": None, "slots": []}

#: Intrinsic pixel sizes, keyed by path and invalidated by the file's mtime.
_size_cache: dict[str, tuple[float, tuple[int | None, int | None]]] = {}


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
    absolute = os.path.join(app.static_folder, relative)
    available = os.path.isfile(absolute)
    resolved = dict(slot)
    resolved["available"] = available
    resolved["url"] = (
        f"{app.static_url_path}/{PHOTO_DIR.replace(os.sep, '/')}/{slot['file']}"
        if available else None
    )
    width, height = _dimensions(absolute) if available else (None, None)
    resolved["width"] = width
    resolved["height"] = height
    resolved["srcset"] = (
        _srcset(app, slot["file"], width) if available and width else None
    )
    return resolved


def _srcset(app: Flask, filename: str, width: int) -> str | None:
    """The narrower copies of this photograph that are actually on disk.

    ``scripts/gen_responsive_images.py`` writes them and skips any width the
    original cannot fill, so which ones exist varies per photograph. Reading the
    directory rather than assuming a fixed ladder keeps the markup honest: a
    ``srcset`` that promises a file the browser then 404s on is worse than no
    ``srcset`` at all.
    """
    base, extension = os.path.splitext(filename)
    if extension.lower() != ".webp":
        return None

    prefix = f"{app.static_url_path}/{PHOTO_DIR.replace(os.sep, '/')}"
    entries = []
    for candidate in VARIANT_WIDTHS:
        if candidate >= width:
            continue
        variant = f"{base}-{candidate}.webp"
        if os.path.isfile(os.path.join(app.static_folder, PHOTO_DIR, variant)):
            entries.append(f"{prefix}/{variant} {candidate}w")
    if not entries:
        return None
    entries.append(f"{prefix}/{filename} {width}w")
    return ", ".join(entries)


def _dimensions(path: str) -> tuple[int | None, int | None]:
    """The photograph's own pixel size, so the template can reserve its space.

    An ``<img>`` with no width and height is a hole of unknown height until the
    file arrives, and everything below it jumps when it does. Read from the file
    rather than declared in the manifest: a number typed next to a photograph is
    a number that goes stale the first time the photograph is replaced.

    Cached per file: this runs for every slot on every request, and decoding a
    dozen headers each time would cost more than the layout shift it prevents.
    """
    try:
        stamp = os.path.getmtime(path)
    except OSError:
        return (None, None)
    hit = _size_cache.get(path)
    if hit and hit[0] == stamp:
        return hit[1]
    try:
        from PIL import Image

        with Image.open(path) as image:
            size = image.size
    except Exception:
        size = (None, None)
    _size_cache[path] = (stamp, size)
    return size


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
