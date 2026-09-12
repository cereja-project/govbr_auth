"""Presentation contracts for the separately loaded local debug interface."""

import base64
import hashlib
import re

import pytest

from govbr_auth.fake.debug.presentation import render_debug_page, page_headers
from govbr_auth.presentation import render_demo_page
from govbr_auth.runtime import GovBrProvider


def test_debug_assets_are_local_responsive_and_respect_reduced_motion():
    html = render_debug_page("/custom/login")
    for marker in (
        "Painel técnico",
        "Reprodução didática",
        "Modo debug",
        'id="steps"',
        'id="export"',
        'id="play"',
        'id="next"',
        'id="replay"',
        'id="speed"',
        'role="tablist"',
        'aria-live="polite"',
        "prefers-reduced-motion",
        "@media",
        '"login": "/custom/login"',
    ):
        assert marker in html
    assert "https://" not in html
    assert "<iframe" not in html
    assert "innerHTML" not in html
    assert "localStorage" not in html
    assert "sessionStorage" not in html
    assert "textContent" in html
    assert "__STYLE__" not in html and "__SCRIPT__" not in html
    assert "[oculto]" in html


def test_script_csp_matches_exact_inline_bytes_and_blocks_remote_content():
    html = render_debug_page("/auth/govbr/login")
    headers = page_headers(html)
    script = re.search(r"<script>(.*?)</script>", html, re.DOTALL)[1]
    digest = base64.b64encode(hashlib.sha256(script.encode()).digest()).decode()
    assert f"script-src 'sha256-{digest}'" in headers["Content-Security-Policy"]
    assert "unsafe-eval" not in headers["Content-Security-Policy"]
    assert "connect-src 'self'" in headers["Content-Security-Policy"]
    assert headers["Cache-Control"] == "no-store"
    assert headers["Referrer-Policy"] == "no-referrer"


def test_debug_configuration_cannot_close_the_inline_script():
    page = render_debug_page("/auth/<script>/login")
    assert page.count("<script>") == 1
    assert '"login": "/auth/\\u003cscript\\u003e/login"' in page
    with pytest.raises(ValueError):
        render_debug_page("https://external.test/login")


def test_normal_demo_does_not_load_debug_assets_and_official_has_no_switch():
    fake = render_demo_page(provider=GovBrProvider.FAKE, login_path="/login")
    official = render_demo_page(provider=GovBrProvider.OFFICIAL, login_path="/login")
    assert 'aria-label="Ativar modo debug"' in fake
    assert "/govbr-auth-demo/debug" not in official
    assert "DEMO_CONFIG" not in fake
    assert "fetch(" not in fake
    assert '<a class="primary" href="/login">' in fake
