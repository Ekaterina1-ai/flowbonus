"""Точка входа для WSGI-сервера: waitress-serve --call ... не нужен, объект уже готов."""
from app import app

application = app

__all__ = ["app", "application"]
