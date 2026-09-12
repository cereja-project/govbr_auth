"""Allowlisted trace projections; never retain raw authentication material."""

import json
from collections.abc import Mapping, Sequence
from http.cookies import CookieError, SimpleCookie
from urllib.parse import parse_qs, urlsplit

HIDDEN = "[oculto]"
_FIELDS = frozenset(
    "response_type client_id redirect_uri scope state nonce code_challenge "
    "code_challenge_method request cpf password code grant_type code_verifier "
    "access_token id_token refresh_token token_type expires_in sub name email "
    "email_verified picture phone_number phone_number_verified error error_description "
    "post_logout_redirect_uri iss aud exp iat nbf auth_time amr acr azp keys".split()
)
_ERRORS = frozenset(
    "invalid_request invalid_client invalid_grant invalid_token access_denied "
    "invalid_state invalid_callback expired_transaction invalid_id_token "
    "provider_rejected provider_unavailable govbr_auth_error".split()
)
_PUBLIC = {
    "response_type": {"code"},
    "code_challenge_method": {"S256"},
    "grant_type": {"authorization_code"},
    "token_type": {"Bearer"},
    "error": _ERRORS,
}


def fields(values: Mapping[str, object]) -> dict[str, object]:
    """Expose schema and protocol constants, never user-controlled free text."""
    result: dict[str, object] = {}
    for key in sorted(_FIELDS.intersection(values)):
        value = values[key]
        if isinstance(value, (list, tuple)):
            value = value[0] if len(value) == 1 else None
        if isinstance(value, str) and value in _PUBLIC.get(key, ()):
            result[key] = value
        elif (
            key == "scope"
            and isinstance(value, str)
            and set(value.split()) <= {"openid", "profile", "email", "phone", "address"}
        ):
            result[key] = " ".join(dict.fromkeys(value.split()))
        elif key == "keys":
            result[key] = "[conjunto de chaves públicas; valores omitidos]"
        else:
            result[key] = HIDDEN
    return result


def body(content: bytes, content_type: str) -> dict[str, object]:
    """Project small known bodies without keeping raw bytes or unknown fields."""
    if len(content) > 65_536:
        return {"body": "[corpo excede o limite de captura]"}
    try:
        if content_type.split(";", 1)[0] == "application/json":
            values = json.loads(content)
        elif content_type.split(";", 1)[0] == "application/x-www-form-urlencoded":
            values = parse_qs(content.decode("utf-8"), keep_blank_values=True)
        else:
            return {"body": "[corpo não capturado]"}
    except (ValueError, UnicodeError):
        return {"body": "[corpo não capturado]"}
    return (
        fields(values)
        if isinstance(values, dict)
        else {"body": "[corpo não capturado]"}
    )


def location(value: str, paths: Mapping[str, str]) -> dict[str, object]:
    """Discard hosts and unknown destinations; redact all control parameters."""
    try:
        parsed = urlsplit(value)
        path = parsed.path if parsed.path in paths else "[destino omitido]"
        query = fields(parse_qs(parsed.query[:16_384], keep_blank_values=True))
    except ValueError:
        return {"path": "[destino omitido]"}
    return {"path": path, "query": query}


def headers(
    values: Sequence[tuple[str, str]], paths: Mapping[str, str]
) -> dict[str, object]:
    """Keep only safe header semantics, including cookie flags but not values."""
    result: dict[str, object] = {}
    cookies = []
    for key, value in values[:32]:
        key = key.lower()
        if key == "location":
            result["Location"] = location(value, paths)
        elif key == "authorization":
            scheme = value.split(" ", 1)[0]
            result["Authorization"] = (
                scheme + " " if scheme in {"Basic", "Bearer"} else ""
            ) + HIDDEN
        elif key == "cookie":
            result["Cookie"] = "[nomes dinâmicos e valores omitidos]"
        elif key == "set-cookie":
            parsed = SimpleCookie()
            try:
                parsed.load(value[:8192])
            except CookieError:
                continue
            for name, morsel in list(parsed.items())[:8]:
                cookies.append(
                    {
                        "name": (
                            "prova do navegador" if "govbr-auth-" in name else "cookie"
                        ),
                        "value": HIDDEN,
                        "HttpOnly": bool(morsel["httponly"]),
                        "Secure": bool(morsel["secure"]),
                        "host_only": not bool(morsel["domain"]),
                        "Path": "/" if morsel["path"] == "/" else HIDDEN,
                        "SameSite": (
                            morsel["samesite"].lower()
                            if morsel["samesite"].lower() in {"lax", "strict", "none"}
                            else HIDDEN
                        ),
                        "removed": morsel["max-age"] == "0",
                    }
                )
        elif key == "content-type":
            mime = value.split(";", 1)[0]
            result["Content-Type"] = (
                mime
                if mime
                in {
                    "application/json",
                    "text/html",
                    "application/x-www-form-urlencoded",
                }
                else HIDDEN
            )
        elif key in {"cache-control", "pragma"}:
            result[key] = (
                value
                if value in {"no-store", "no-cache", "no-store, no-cache"}
                else HIDDEN
            )
        elif key == "www-authenticate":
            result["WWW-Authenticate"] = (
                value.split(" ", 1)[0]
                if value.split(" ", 1)[0] in {"Basic", "Bearer"}
                else HIDDEN
            )
    if cookies:
        result["Set-Cookie"] = cookies
    return result
