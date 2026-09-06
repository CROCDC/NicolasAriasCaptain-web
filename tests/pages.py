"""The page list and the viewport matrix, in one place.

Single source of truth so the browser tests and anything added later cannot
drift apart on which pages the site has.
"""

from __future__ import annotations

#: Every public path the app serves as a page.
PUBLIC_PAGES: list[str] = [
    "/",
]

#: (name, width, height): mobile, large mobile, tablet portrait, tablet
#: landscape, desktop.
VIEWPORTS: list[tuple[str, int, int]] = [
    ("mobile-375", 375, 667),
    ("mobile-414", 414, 896),
    ("tablet-768", 768, 1024),
    ("tablet-1024", 1024, 768),
    ("desktop-1280", 1280, 720),
]


def page_slug(path: str) -> str:
    """Filesystem-safe name for a path ('/' -> 'home')."""
    return path.strip("/").replace("/", "_") or "home"
