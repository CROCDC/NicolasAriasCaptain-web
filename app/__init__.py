"""Capitán Nicolás Arias application package."""

from app.factory import create_app

app = create_app()

__all__ = ["app", "create_app"]
