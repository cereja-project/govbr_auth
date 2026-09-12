"""Locally packaged debug interface with safe configuration and a script CSP."""

import base64
import hashlib
import json
import re
from functools import lru_cache
from importlib.resources import files

from govbr_auth.fake.debug.controller import DEBUG_PATH, SAFE_HEADERS
from govbr_auth.presentation import (
    _render_brand_signature,
    _validate_internal_absolute_path,
)


@lru_cache(maxsize=3)
def _asset(name: str) -> str:
    return (
        files("govbr_auth")
        .joinpath("_assets", "demo", name)
        .read_text(encoding="utf-8")
    )


def render_debug_page(login_path: str) -> str:
    _validate_internal_absolute_path(login_path)
    config = (
        json.dumps(
            {
                "login": login_path,
                "trace": DEBUG_PATH + "/trace",
                "home": "/govbr-auth-demo",
            }
        )
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )
    return (
        _asset("debug.html")
        .replace("__BRAND__", _render_brand_signature())
        .replace("__STYLE__", _asset("debug.css"))
        .replace(
            "__SCRIPT__", "const DEMO_CONFIG = " + config + ";\n" + _asset("debug.js")
        )
    )


def page_headers(page: str) -> dict[str, str]:
    script = re.search(r"<script>(.*?)</script>", page, re.DOTALL)[1]
    digest = base64.b64encode(hashlib.sha256(script.encode()).digest()).decode()
    return SAFE_HEADERS | {
        "Content-Security-Policy": (
            "default-src 'none'; script-src 'sha256-" + digest + "'; "
            "style-src 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; "
            "base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
        )
    }
