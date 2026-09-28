"""Точка входу: `uv run uvicorn app.api.main:app --workers 1`. Креди — лише з env."""

from app.api.app import create_app

app = create_app()
