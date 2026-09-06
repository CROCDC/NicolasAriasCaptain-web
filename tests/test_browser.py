"""The site in a real browser: layout at every width, and the flows JS owns.

Marked slow — these drive Firefox. They skip with a reason when Playwright or
its browser is not installed, and `make browser` is what installs it.
"""

from __future__ import annotations

from typing import Any

import pytest

from pages import PUBLIC_PAGES, VIEWPORTS

pytestmark = pytest.mark.slow


def _overflows(page: Any) -> int:
    """Pixels the document scrolls sideways. Anything above 1 is a layout bug."""
    return page.evaluate(
        "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
    )


@pytest.mark.parametrize("path", PUBLIC_PAGES)
@pytest.mark.parametrize("name,width,height", VIEWPORTS)
def test_no_horizontal_scroll_anywhere(
    page: Any, live_server: str, path: str, name: str, width: int, height: int
) -> None:
    page.set_viewport_size({"width": width, "height": height})
    page.goto(f"{live_server}{path}", wait_until="networkidle")
    assert _overflows(page) <= 1, f"{path} scrolls sideways at {name}"


def test_the_portada_is_readable_on_a_phone(page: Any, live_server: str) -> None:
    page.set_viewport_size({"width": 375, "height": 667})
    page.goto(live_server, wait_until="networkidle")

    title = page.locator("h1.portada-name")
    assert title.is_visible()
    assert "Nicolás Arias" in title.inner_text()
    # The reveal animation must have run: a page whose content never becomes
    # visible is the failure mode this design is exposed to.
    page.wait_for_selector("h1.portada-name.visible", timeout=5000)


@pytest.mark.parametrize("width,height", [(375, 667), (1280, 800)])
def test_the_index_opens_and_closes_at_every_width(
    page: Any, live_server: str, width: int, height: int
) -> None:
    # The bar carries no section links, so this overlay is the whole
    # navigation — on a phone and on a desktop alike.
    page.set_viewport_size({"width": width, "height": height})
    page.goto(live_server, wait_until="networkidle")

    opener = page.locator("#menuOpen")
    opener.click()
    page.wait_for_selector("#menu.open")
    assert opener.get_attribute("aria-expanded") == "true"
    assert page.locator("#menu .menu-link").first.is_visible()

    page.keyboard.press("Escape")
    page.wait_for_selector("#menu:not(.open)")
    assert opener.get_attribute("aria-expanded") == "false"


def test_a_section_link_closes_the_index_and_goes_there(
    page: Any, live_server: str
) -> None:
    page.goto(live_server, wait_until="networkidle")

    page.locator("#menuOpen").click()
    page.wait_for_selector("#menu.open")
    page.locator('.menu-link[href="#servicios"]').click()

    page.wait_for_selector("#menu:not(.open)")
    page.wait_for_function(
        "() => Math.abs(document.querySelector('#servicios')"
        ".getBoundingClientRect().top) < 120",
        timeout=5000,
    )


def test_a_service_link_preselects_the_form(page: Any, live_server: str) -> None:
    page.goto(live_server, wait_until="networkidle")
    page.locator('[data-service="traslado"]').click()
    assert page.locator("#service_type").input_value() == "traslado"


def test_the_contact_form_stores_an_enquiry(
    page: Any, live_server: str, app_instance: Any
) -> None:
    page.goto(live_server, wait_until="networkidle")

    page.fill("#name", "Julián Ferrer")
    page.fill("#email", "julian@example.com")
    page.select_option("#service_type", "salida")
    page.fill("#message", "Quiero una salida al atardecer para cuatro personas.")
    page.click("#submitBtn")

    page.wait_for_selector("#formSuccess:not([hidden])", timeout=8000)
    assert "Recibí tu mensaje" in page.inner_text("#formSuccess")

    with app_instance.app_context():
        from app.repositories import ContactRepository

        stored = ContactRepository.get_all()
        assert len(stored) == 1
        assert stored[0].email == "julian@example.com"


def test_an_invalid_form_never_reaches_the_server(
    page: Any, live_server: str, app_instance: Any
) -> None:
    page.goto(live_server, wait_until="networkidle")

    page.fill("#name", "Sin email")
    page.fill("#message", "Consulta sin correo.")
    page.click("#submitBtn")

    page.wait_for_selector("#emailError:not(:empty)", timeout=4000)

    with app_instance.app_context():
        from app.repositories import ContactRepository

        assert ContactRepository.get_all() == []
