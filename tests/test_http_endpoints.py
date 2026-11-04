"""What every public URL answers, including the ones nobody looks at."""

from __future__ import annotations

from typing import Any

from pages import PUBLIC_PAGES


def test_every_public_page_renders(client: Any) -> None:
    for path in PUBLIC_PAGES:
        response = client.get(path)
        assert response.status_code == 200, f"{path} answered {response.status_code}"
        assert b"<html" in response.data.lower()


def test_home_carries_the_name_and_the_contact_form(client: Any) -> None:
    body = client.get("/").get_data(as_text=True)
    assert "Nicolás Arias" in body
    assert 'id="contactForm"' in body
    # The critical CSS is inlined rather than linked; a page that lost it would
    # still be 200 and would paint unstyled.
    assert "--copper" in body


def test_the_short_admin_addresses_reach_the_panel(client: Any) -> None:
    # The headers the tunnel forwards: http, but on port 443. An absolute
    # redirect built from them sends the browser to http://host:443/.
    proxied = {"X-Forwarded-Proto": "http", "X-Forwarded-Port": "443",
               "X-Forwarded-Host": "orzadelplata.com.ar"}
    for path in ("/admin", "/admin/", "/admin/content"):
        response = client.get(path, headers=proxied)
        assert response.status_code == 302, f"{path} answered {response.status_code}"
        assert response.headers["Location"] == "/admin/content/", path


def test_health_is_json_ok(client: Any) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


def test_robots_points_at_the_sitemap(client: Any) -> None:
    body = client.get("/robots.txt").get_data(as_text=True)
    assert "User-agent: *" in body
    assert "/sitemap.xml" in body


def test_sitemap_lists_the_home_page(client: Any) -> None:
    response = client.get("/sitemap.xml")
    assert response.status_code == 200
    assert "<urlset" in response.get_data(as_text=True)


def test_favicon_is_served(client: Any) -> None:
    response = client.get("/favicon.ico")
    assert response.status_code == 200
    assert "svg" in response.content_type


def test_unknown_path_gets_the_site_404(client: Any) -> None:
    response = client.get("/no-existe")
    assert response.status_code == 404
    body = response.get_data(as_text=True)
    # Not the Werkzeug default page: a wrong turn still lands on the site.
    assert "404" in body
    assert "Volver al inicio" in body


def test_static_assets_are_cached_for_a_year(client: Any) -> None:
    response = client.get("/static/css/style-deferred.css")
    assert response.status_code == 200
    assert response.cache_control.max_age == 60 * 60 * 24 * 365
