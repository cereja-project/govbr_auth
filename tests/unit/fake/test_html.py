from pydantic import SecretStr

from govbr_auth.fake._html import render_fake_login
from govbr_auth.fake.provider import FakeAuthorizationSession


def test_fake_login_has_accessible_native_fields_and_warning() -> None:
    page = render_fake_login(
        FakeAuthorizationSession(request=SecretStr("opaque-request")),
        login_action="/fake-govbr/login",
    )

    assert 'method="post"' in page
    assert 'action="/fake-govbr/login"' in page
    assert 'name="cpf"' in page and 'label for="cpf"' in page
    assert 'name="password"' in page and 'label for="password"' in page
    assert 'type="password"' in page
    assert 'autocomplete="username"' in page
    assert 'autocomplete="current-password"' in page
    assert 'aria-describedby="fake-guidance"' in page
    assert ":focus-visible" in page
    assert "SIMULAÇÃO LOCAL" in page
    assert "Não informe credenciais reais" in page
    assert "opaque-request" in page


def test_fake_login_escapes_action_and_never_renders_password() -> None:
    page = render_fake_login(
        FakeAuthorizationSession(request=SecretStr("opaque-request")),
        login_action='"><script>alert(1)</script>',
        invalid_credentials=True,
    )

    assert "<script>" not in page
    assert "CPF ou senha inválidos" in page
    assert 'role="alert"' in page
