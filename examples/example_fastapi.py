"""FastAPI consumer using the canonical govbr-auth facade."""

from collections.abc import Callable
from datetime import UTC, datetime

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import JSONResponse, Response

from govbr_auth.fastapi import AuthContext, GovBrAuth


def utc_now() -> datetime:
    """Return the current UTC time for the example's injectable clock."""
    return datetime.now(UTC)


def create_app(*, clock: Callable[[], datetime] = utc_now) -> FastAPI:
    """Create the same consumer for the official or selected fake provider."""
    load_dotenv(override=False)
    application = FastAPI()

    async def authenticated(context: AuthContext) -> Response:
        return JSONResponse({"authenticated": True})

    auth = GovBrAuth(on_success=authenticated, clock=clock)
    application.include_router(auth.router)
    return application
