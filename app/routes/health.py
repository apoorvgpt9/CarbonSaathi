"""Health-check route for CarbonSaathi."""

from __future__ import annotations

from importlib.metadata import version
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    """Response schema for the health-check endpoint."""

    status: Literal["ok"]
    version: str


@router.get("/health")
async def health() -> HealthResponse:
    """Return the application liveness status and version.

    Returns:
        A :class:`HealthResponse` with ``status="ok"`` and the package version
        read from the installed distribution metadata.
    """
    return HealthResponse(status="ok", version=version("carbonsaathi"))
