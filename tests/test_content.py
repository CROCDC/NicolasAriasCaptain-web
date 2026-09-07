"""The editable copy: that the registry and the templates agree.

A key is the primary key of an override row, so the two ways this drifts are
both silent. A ``t('typo')`` in a template is caught by the library, which
raises on an unknown key outside production rather than rendering an empty
heading. The other direction is not caught by anything: a registry entry no
template uses is a field the captain can edit, save, and never see change.
"""

from __future__ import annotations

import os
import re
from typing import Any

from app.content import REGISTRY

#: The photographs are resolved in Python (app/services/media.py builds the key
#: from the manifest id), not written out in a template, so the template scan
#: below cannot see them. They get their own check instead of an exemption.
PHOTO_GROUP = "fotos"

TEMPLATE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app", "templates")

#: Every t-flavoured global takes the key as its first argument.
_CALL = re.compile(r"\bt(?:_lines|_plain|_optional|_list)?\(\s*'([^']+)'")


def _registry_keys(skip: str = "") -> list[str]:
    return [field.key
            for group in REGISTRY.groups
            for section in group.sections
            for field in section.fields
            if group.key != skip]


def _template_keys() -> set[str]:
    keys: set[str] = set()
    for name in os.listdir(TEMPLATE_DIR):
        if not name.endswith(".html"):
            continue
        with open(os.path.join(TEMPLATE_DIR, name), encoding="utf-8") as handle:
            keys.update(_CALL.findall(handle.read()))
    return keys


def test_keys_are_unique() -> None:
    keys = _registry_keys()
    duplicates = {key for key in keys if keys.count(key) > 1}
    assert not duplicates, f"the same key is declared twice: {sorted(duplicates)}"


def test_every_template_key_is_declared() -> None:
    undeclared = _template_keys() - set(_registry_keys())
    assert not undeclared, (
        f"templates ask for keys the registry does not declare: {sorted(undeclared)}")


def test_every_declared_key_is_used() -> None:
    unused = set(_registry_keys(skip=PHOTO_GROUP)) - _template_keys()
    assert not unused, (
        "the panel offers fields no template renders — editing one of these "
        f"would change nothing: {sorted(unused)}")


def test_every_photograph_is_offered_exactly_once(app_context: Any) -> None:
    """The photo fields and the manifest have to describe the same set.

    They are built from the manifest, so this only fails if that stops being
    true — a field for a photograph the site no longer declares is a panel entry
    that edits nothing, and a slot with no field is a photograph nobody can
    replace.
    """
    from app.services import media

    declared = {field.key.removeprefix("foto.")
                for group in REGISTRY.groups if group.key == PHOTO_GROUP
                for section in group.sections
                for field in section.fields}
    slots = {slot["id"] for slot in media.load_manifest(app_context)}
    assert declared == slots, (
        f"only in the panel: {sorted(declared - slots)}; "
        f"only in the manifest: {sorted(slots - declared)}")


def test_defaults_are_what_the_page_shows(client: Any) -> None:
    """A default is the text the site had; the table only holds changes.

    With no overrides the pages have to read exactly as before, which is what
    makes an empty database safe and "restore the original" a row delete. Both
    pages, because the 404's copy is only ever on the 404.
    """
    body = (client.get("/").get_data(as_text=True)
            + client.get("/no-existe").get_data(as_text=True))
    missing = [
        field.key
        for group in REGISTRY.groups
        for section in group.sections
        for field in section.fields
        if field.type == "line" and field.default not in body
    ]
    assert not missing, f"defaults that never reached a page: {missing}"
