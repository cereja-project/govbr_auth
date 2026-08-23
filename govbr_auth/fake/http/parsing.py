"""Pure parsing helpers for the FakeGov HTTP adapter."""

import base64
import binascii
from collections.abc import Mapping

from pydantic import SecretStr

from govbr_auth.fake.provider import FakeClientCredentials


def required_text_values(
    values: Mapping[str, object],
    names: tuple[str, ...],
) -> dict[str, str] | None:
    """Return required nonblank text fields or ``None`` at the HTTP boundary."""
    parsed: dict[str, str] = {}
    for name in names:
        value = values.get(name)
        if not isinstance(value, str) or not value.strip():
            return None
        parsed[name] = value
    return parsed


def parse_basic_authorization(value: str | None) -> FakeClientCredentials | None:
    """Parse a strict Basic credential header."""
    encoded = _parse_authorization_scheme(value, scheme="Basic")
    if encoded is None:
        return None
    try:
        decoded = base64.b64decode(encoded, validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return None
    client_id, separator, client_secret = decoded.partition(":")
    if not separator or not client_id.strip() or not client_secret.strip():
        return None
    return FakeClientCredentials(
        client_id=client_id,
        client_secret=SecretStr(client_secret),
    )


def parse_bearer_authorization(value: str | None) -> SecretStr | None:
    """Parse a strict Bearer token header without exposing the token."""
    token = _parse_authorization_scheme(value, scheme="Bearer")
    if token is None or any(character.isspace() for character in token):
        return None
    return SecretStr(token)


def _parse_authorization_scheme(value: str | None, *, scheme: str) -> str | None:
    """Return credentials from one bounded, exact authorization scheme."""
    if value is None or len(value) > 8192:
        return None
    parsed_scheme, separator, credentials = value.partition(" ")
    if (
        not separator
        or parsed_scheme.casefold() != scheme.casefold()
        or not credentials
        or credentials != credentials.strip()
    ):
        return None
    return credentials
