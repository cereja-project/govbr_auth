"""Render self-contained HTML pages for the local Fake Gov.br provider."""

import html
from govbr_auth.fake.provider import FakeAuthorizationSession
from govbr_auth.presentation import render_page


def render_fake_login(
    session: FakeAuthorizationSession,
    *,
    login_action: str,
    invalid_credentials: bool = False,
) -> str:
    """Render the local CPF and password login form."""
    request_value = html.escape(session.request.get_secret_value(), quote=True)
    action_value = html.escape(login_action, quote=True)
    credential_error = (
        '<p class="error" role="alert">CPF ou senha inválidos.</p>'
        if invalid_credentials
        else ""
    )
    content = (
        "<h1>FAKE / SIMULAÇÃO</h1>"
        '<p id="fake-guidance" class="warning"><strong>Atenção:</strong> '
        "Não informe credenciais reais. Este provedor é somente para testes locais.</p>"
        f"{credential_error}"
        f'<form method="post" action="{action_value}">'
        f'<input type="hidden" name="request" value="{request_value}">'
        '<label for="cpf">CPF</label>'
        '<input id="cpf" name="cpf" type="text" inputmode="numeric" '
        'autocomplete="username" aria-describedby="fake-guidance" required>'
        '<label for="password">Senha</label>'
        '<input id="password" name="password" type="password" '
        'autocomplete="current-password" aria-describedby="fake-guidance" required>'
        '<button type="submit">Entrar</button>'
        "</form>"
    )
    return render_page(title="FAKE / SIMULAÇÃO", body=content, layout="card")
