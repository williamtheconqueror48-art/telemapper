"""Vercel serverless entrypoint. Vercel's Python runtime serves the
ASGI app exported as `app` from api/index.py."""

from app.api import app  # noqa: F401  (re-exported for Vercel)
