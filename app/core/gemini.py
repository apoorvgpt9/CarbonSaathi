"""Lazy Gemini (google-generativeai) client initialisation for CarbonSaathi.

Mirrors the Firebase lazy-init pattern in :mod:`app.core.firebase`: the SDK is
configured **at most once** per process and only on first use, never at import
time.  This keeps imports side-effect free (no API key needed to import the
module) and avoids blocking work during Cloud Run cold starts.

Usage::

    from app.core.gemini import get_gemini_client

    factory = get_gemini_client()
    model = factory.flash(system_instruction="...", tools=[...])
    response = await model.generate_content_async("...")
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import google.generativeai as genai

from app.core.config import get_settings


class GenerativeModelFactory:
    """Builds configured Gemini models on demand.

    The factory holds only the configured model names and constructs a fresh
    :class:`google.generativeai.GenerativeModel` per call so that callers may
    attach call-specific ``system_instruction`` and ``tools``.

    Args:
        flash_model: Model name used for the fast Logger agent.
        pro_model: Model name used for the Analyst and Coach agents.
    """

    def __init__(self, *, flash_model: str, pro_model: str) -> None:
        """Store the configured model names."""
        self._flash_model = flash_model
        self._pro_model = pro_model

    def flash(
        self,
        *,
        system_instruction: str | None = None,
        tools: list[Any] | None = None,
    ) -> Any:
        """Build a Gemini 2.5 Flash model.

        Args:
            system_instruction: Optional system prompt baked into the model.
            tools: Optional list of function declarations / tools for function
                calling.

        Returns:
            A configured :class:`google.generativeai.GenerativeModel`.
        """
        return genai.GenerativeModel(
            model_name=self._flash_model,
            system_instruction=system_instruction,
            tools=tools,
        )

    def pro(
        self,
        *,
        system_instruction: str | None = None,
        tools: list[Any] | None = None,
    ) -> Any:
        """Build a Gemini 2.5 Pro model.

        Args:
            system_instruction: Optional system prompt baked into the model.
            tools: Optional list of function declarations / tools for function
                calling.

        Returns:
            A configured :class:`google.generativeai.GenerativeModel`.
        """
        return genai.GenerativeModel(
            model_name=self._pro_model,
            system_instruction=system_instruction,
            tools=tools,
        )


@lru_cache(maxsize=1)
def get_gemini_client() -> GenerativeModelFactory:
    """Return the process-wide :class:`GenerativeModelFactory`.

    On first call this configures the ``google-generativeai`` SDK with the API
    key from settings, so ``genai.configure`` runs exactly once per process.
    Call ``get_gemini_client.cache_clear()`` to force re-initialisation (used in
    tests).

    Returns:
        The cached :class:`GenerativeModelFactory` instance.
    """
    settings = get_settings()
    genai.configure(api_key=settings.gemini_api_key.get_secret_value())
    return GenerativeModelFactory(
        flash_model=settings.gemini_model_flash,
        pro_model=settings.gemini_model_pro,
    )
