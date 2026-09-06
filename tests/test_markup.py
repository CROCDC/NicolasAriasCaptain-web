"""What the rendered HTML has to be true of, checked without a browser.

These are the accessibility and SEO basics that are cheap to get right and
expensive to notice missing: one h1, every image described, every field
labelled, every new-tab link safe.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Any

from pages import PUBLIC_PAGES


class _Collector(HTMLParser):
    """Gathers just enough of the document to assert about it."""

    def __init__(self) -> None:
        super().__init__()
        self.tags: list[tuple[str, dict[str, str]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append((tag, {key: (value or "") for key, value in attrs}))

    def of(self, tag: str) -> list[dict[str, str]]:
        return [attrs for name, attrs in self.tags if name == tag]


def _parse(client: Any, path: str) -> _Collector:
    parser = _Collector()
    parser.feed(client.get(path).get_data(as_text=True))
    return parser


def test_pages_declare_spanish(client: Any) -> None:
    for path in PUBLIC_PAGES:
        body = client.get(path).get_data(as_text=True)
        assert '<html lang="es">' in body


def test_exactly_one_h1_per_page(client: Any) -> None:
    for path in PUBLIC_PAGES:
        body = client.get(path).get_data(as_text=True)
        assert len(re.findall(r"<h1[\s>]", body)) == 1, path


def test_every_image_is_described(client: Any) -> None:
    for path in PUBLIC_PAGES:
        for image in _parse(client, path).of("img"):
            assert image.get("alt", "").strip(), f"{path}: <img> without alt"


def test_every_field_has_a_label(client: Any) -> None:
    parser = _parse(client, "/")
    labelled = {label["for"] for label in parser.of("label") if "for" in label}

    for tag in ("input", "textarea", "select"):
        for field in parser.of(tag):
            if field.get("type") in {"hidden", "submit"}:
                continue
            assert field.get("id") in labelled, f"{tag} {field.get('id')} has no label"


def test_links_that_open_a_new_tab_cannot_reach_back(client: Any) -> None:
    for path in PUBLIC_PAGES:
        for link in _parse(client, path).of("a"):
            if link.get("target") == "_blank":
                assert "noopener" in link.get("rel", ""), link.get("href")


def test_the_page_says_what_it_is_when_shared(client: Any) -> None:
    body = client.get("/").get_data(as_text=True)
    for tag in ('property="og:title"', 'property="og:description"',
                'property="og:url"', 'name="twitter:card"'):
        assert tag in body


def test_contact_details_come_from_the_one_config_file(
    client: Any, app_instance: Any
) -> None:
    body = client.get("/").get_data(as_text=True)
    site = app_instance.config["SITE"]
    assert site["email"] in body
    assert site["whatsapp"]["display"] in body
    assert f'wa.me/{site["whatsapp"]["number"]}' in body


def test_the_form_offers_exactly_the_services_the_server_accepts(client: Any) -> None:
    from app.routes import VALID_SERVICE_TYPES

    options = {
        option["value"] for option in _parse(client, "/").of("option")
        if option.get("value")
    }
    assert options == VALID_SERVICE_TYPES
