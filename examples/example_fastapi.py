"""FastAPI consumer using the canonical govbr-auth facade."""

import os
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import JSONResponse, Response
from pydantic import SecretStr

from govbr_auth.core import GovBrSettings, ProviderEnvironment
from govbr_auth.fastapi import AuthContext, GovBrAuth


def utc_now() -> datetime:
    """Return the current UTC time for the example's injectable clock."""
    return datetime.now(UTC)


def settings_from_environment() -> GovBrSettings:
    """Load the official-provider settings used by configuration examples."""
    load_dotenv(dotenv_path=Path.cwd() / ".env", override=False)
    return GovBrSettings(
        environment=ProviderEnvironment(
            os.environ.get("GOVBR_ENVIRONMENT", "production")
        ),
        authorization_url=os.environ["GOVBR_AUTHORIZATION_URL"],
        token_url=os.environ["GOVBR_TOKEN_URL"],
        userinfo_url=os.environ["GOVBR_USERINFO_URL"],
        client_id=os.environ["GOVBR_CLIENT_ID"],
        client_secret=SecretStr(os.environ["GOVBR_CLIENT_SECRET"]),
        redirect_uri=os.environ["GOVBR_REDIRECT_URI"],
        transaction_secret=SecretStr(os.environ["GOVBR_TRANSACTION_SECRET"]),
        issuer=os.environ["GOVBR_ISSUER"],
        jwks_url=os.environ["GOVBR_JWKS_URL"],
    )


def create_app(*, clock: Callable[[], datetime] = utc_now) -> FastAPI:
    """Create the same consumer for the official or selected fake provider."""
    load_dotenv(dotenv_path=Path.cwd() / ".env", override=False)
    application = FastAPI()

    async def authenticated(context: AuthContext) -> Response:
        return JSONResponse({"authenticated": True, "subject": context.user.subject})

    auth = GovBrAuth(on_success=authenticated, clock=clock)
    application.include_router(auth.router)
    return application
