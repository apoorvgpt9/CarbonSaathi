"""Server-rendered HTML page routes for CarbonSaathi.

Serves the six top-level pages of the Phase 6 frontend.  All pages are
public — authentication happens client-side via the Firebase web SDK
(``app/static/js/auth.js``); API routes under ``/api/*`` continue to enforce
server-side Firebase ID-token verification.

Routing convention
------------------
Unlike the ``/api/*`` routers which use empty-string paths
(``@router.get("")``), this router uses **leading slashes** on every handler.
The slashless convention applies only to *prefixed* routers, where the prefix
is concatenated with the handler path; an unprefixed router serves the literal
path on the request line, and ``GET /`` requires the path string ``"/"``.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.core.templates import get_templates
from app.models.user import IndianState

router = APIRouter(tags=["pages"])


@router.get("/", response_class=HTMLResponse, summary="Sign-in landing page")
async def sign_in(request: Request) -> HTMLResponse:
    """Render the sign-in landing page.

    Args:
        request: The incoming request (required by ``TemplateResponse``).

    Returns:
        The rendered ``sign_in.html`` template.
    """
    return get_templates().TemplateResponse(request, "sign_in.html", {})


@router.get("/onboarding", response_class=HTMLResponse, summary="Onboarding form")
async def onboarding(request: Request) -> HTMLResponse:
    """Render the onboarding form (state + home profile).

    Args:
        request: The incoming request.

    Returns:
        The rendered ``onboarding.html`` template with the
        :class:`~app.models.user.IndianState` enum members supplied as
        ``states`` for the dropdown.
    """
    return get_templates().TemplateResponse(
        request,
        "onboarding.html",
        {"states": [s.value for s in IndianState]},
    )


@router.get("/dashboard", response_class=HTMLResponse, summary="Dashboard")
async def dashboard(request: Request) -> HTMLResponse:
    """Render the dashboard page.

    Args:
        request: The incoming request.

    Returns:
        The rendered ``dashboard.html`` template.
    """
    return get_templates().TemplateResponse(request, "dashboard.html", {})


@router.get("/log", response_class=HTMLResponse, summary="Activity-log form")
async def log_page(request: Request) -> HTMLResponse:
    """Render the natural-language activity logging page.

    Args:
        request: The incoming request.

    Returns:
        The rendered ``log.html`` template.
    """
    return get_templates().TemplateResponse(request, "log.html", {})


@router.get("/insights", response_class=HTMLResponse, summary="Insights & reasoning stream")
async def insights_page(request: Request) -> HTMLResponse:
    """Render the insights page (streams Analyst -> Coach reasoning).

    Args:
        request: The incoming request.

    Returns:
        The rendered ``insights.html`` template.
    """
    return get_templates().TemplateResponse(request, "insights.html", {})


@router.get("/recommendations", response_class=HTMLResponse, summary="Recommendations")
async def recommendations_page(request: Request) -> HTMLResponse:
    """Render the recommendations page.

    Args:
        request: The incoming request.

    Returns:
        The rendered ``recommendations.html`` template.
    """
    return get_templates().TemplateResponse(request, "recommendations.html", {})
