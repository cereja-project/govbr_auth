from govbr_auth.core import GovBrUser
from govbr_auth.demo._html import render_error, render_home, render_success


def test_home_is_a_guided_local_showcase() -> None:
    page = render_home()

    assert "FAKE / SIMULAÇÃO" in page
    assert 'href="/auth/govbr/login"' in page
    assert "sem credenciais Gov.br" in page
    assert ("Redirecionar", "Escolher usuário", "Validar callback") == tuple(
        label for label in ("Redirecionar", "Escolher usuário", "Validar callback") if label in page
    )


def test_success_exposes_only_sanitized_fake_identity() -> None:
    user = GovBrUser(sub="demo-ana", name="Ana Demo", email="ana@example.test")

    page = render_success(user)

    assert all(value in page for value in ("Ana Demo", "demo-ana", "ana@example.test"))
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
