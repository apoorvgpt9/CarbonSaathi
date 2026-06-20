"""Jinja2 templates accessor for CarbonSaathi.

Exposes a single cached :class:`Jinja2Templates` instance pointing at the
``app/templates`` directory.  Routes inject it via FastAPI's dependency
mechanism (or call :func:`get_templates` directly).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from fastapi.templating import Jinja2Templates

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"


@lru_cache(maxsize=1)
def get_templates() -> Jinja2Templates:
    """Return the cached :class:`Jinja2Templates` instance.

    The directory is resolved relative to this module so the lookup works
    regardless of the current working directory at process start.

    Returns:
        A :class:`Jinja2Templates` bound to ``app/templates``.
    """
    return Jinja2Templates(directory=str(_TEMPLATES_DIR))
