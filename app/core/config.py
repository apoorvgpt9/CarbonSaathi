"""Runtime configuration for CarbonSaathi.

Defines the :class:`Settings` model (loaded from environment variables and an
optional ``.env`` file) and a cached :func:`get_settings` accessor implementing
the lazy-initialisation pattern.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Any

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

_VALID_APP_ENVS = {"development", "staging", "production"}
_VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


class Settings(BaseSettings):
    """Application settings sourced from the environment.

    Unknown environment variables are rejected (``extra="forbid"``) so that a
    misspelled variable name fails loudly rather than being silently ignored.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="forbid",
    )

    app_env: str = "development"
    log_level: str = "INFO"
    allowed_origins: Annotated[list[str], NoDecode] = [
        "http://localhost:8080",
        "https://carbonsaathi-ahkpdce5pa-el.a.run.app",
    ]
    gemini_api_key: SecretStr
    gemini_model_flash: str = "gemini-2.5-flash"
    gemini_model_pro: str = "gemini-2.5-pro"
    firebase_project_id: str
    firebase_api_key: str
    firebase_auth_domain: str
    firebase_app_id: str
    google_application_credentials: str = "./serviceAccountKey.json"
    rate_limit_per_minute: int = Field(default=30, ge=1, le=1000)

    @field_validator("app_env")
    @classmethod
    def _validate_app_env(cls, value: str) -> str:
        """Ensure ``app_env`` is one of the supported deployment environments.

        Args:
            value: The raw environment value.

        Returns:
            The validated environment string.

        Raises:
            ValueError: If the value is not a recognised environment.
        """
        if value not in _VALID_APP_ENVS:
            raise ValueError(f"app_env must be one of {sorted(_VALID_APP_ENVS)}, got {value!r}")
        return value

    @field_validator("log_level")
    @classmethod
    def _validate_log_level(cls, value: str) -> str:
        """Normalise and validate the logging level.

        Args:
            value: The raw log level (any case).

        Returns:
            The upper-cased log level.

        Raises:
            ValueError: If the value is not a recognised logging level.
        """
        upper = value.upper()
        if upper not in _VALID_LOG_LEVELS:
            raise ValueError(f"log_level must be one of {sorted(_VALID_LOG_LEVELS)}, got {value!r}")
        return upper

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: Any) -> Any:
        """Split a comma-separated origins string into a list.

        Args:
            value: Either a comma-separated string or an already-parsed list.

        Returns:
            A list of trimmed origin strings, or the value unchanged when it is
            not a string.
        """
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide :class:`Settings` instance.

    The result is cached so settings are constructed exactly once per process.
    Call ``get_settings.cache_clear()`` to force re-evaluation (used in tests).

    Returns:
        The cached settings instance.
    """
    return Settings()
