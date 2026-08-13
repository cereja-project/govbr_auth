from govbr_auth.core import GovBrUser
from govbr_auth.demo._html import render_error, render_home, render_success


def test_home_is_a_guided_local_showcase() -> None:
    page = render_home()

    assert "FAKE / SIMULAÇÃO" in page
    assert 'href="/auth/govbr/login"' in page
    assert "sem credenciais Gov.br" in page
    assert "Redirecionar" in page
    assert "Escolher usuário" in page
    assert "Validar callback" in page


def test_success_exposes_only_sanitized_fake_identity() -> None:
    user = GovBrUser(sub="demo-ana", name="Ana Demo", email="ana@example.test")

    page = render_success(user)

    assert "Ana Demo" in page
    assert "demo-ana" in page
    assert "ana@example.test" in page
    assert 'href="/auth/govbr/login"' in page
    assert "access_token" not in page
    assert "id_token" not in page


def test_success_escapes_user_derived_values() -> None:
    user = GovBrUser(
        sub='<script>alert("subject")</script>',
        name='<img src=x onerror=alert("name")>',
        email='ana&demo@example.test',
    )

    page = render_success(user)

    assert '<script>alert("subject")</script>' not in page
    assert '<img src=x onerror=alert("name")>' not in page
    assert "ana&amp;demo@example.test" in page
    assert "&lt;script&gt;alert(&quot;subject&quot;)&lt;/script&gt;" in page
    assert "&lt;img src=x onerror=alert(&quot;name&quot;)&gt;" in page


def test_error_uses_stable_code_without_internal_detail() -> None:
    page = render_error(code="invalid_state", status_code=400)

    assert "invalid_state" in page
    assert "Tente iniciar novamente" in page
    assert "traceback" not in page.casefold()


def test_error_replaces_unknown_code_that_could_contain_a_secret() -> None:
    secret = "access_token=secret-value"

    page = render_error(code=secret, status_code=502)

    assert "govbr_auth_error" in page
    assert secret not in page
