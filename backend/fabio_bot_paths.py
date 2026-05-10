"""Fabio_bot project root (parent of backend/, frontend/, portal/)."""

from __future__ import annotations

from pathlib import Path


def fabio_bot_root() -> Path:
    """Directory containing backend/, frontend/, portal/, and typically ``.env``."""
    return Path(__file__).resolve().parent.parent
