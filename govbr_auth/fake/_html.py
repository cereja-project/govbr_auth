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
        '<div class="message danger"><strong>Não foi possível entrar</strong>'
        '<p id="credential-error" class="error" role="alert">'
        "CPF ou senha inválidos.</p></div>"
        if invalid_credentials
        else ""
    )
    described_by = (
        "fake-guidance credential-error" if invalid_credentials else "fake-guidance"
    )
    cpf_described_by = described_by.replace("fake-guidance", "fake-guidance cpf-hint")
    invalid_state = ' aria-invalid="true"' if invalid_credentials else ""
    content = (
        "<h1>FAKE / SIMULAÇÃO</h1>"
        '<div id="fake-guidance" class="message warning" role="note">'
        "<strong>Ambiente de simulação</strong>Não informe credenciais reais. "
        "Este provedor é somente para testes locais.</div>"
        f"{credential_error}"
        f'<form method="post" action="{action_value}">'
        f'<input type="hidden" name="request" value="{request_value}">'
        '<label for="cpf">CPF</label>'
        '<span id="cpf-hint" class="field-hint">Somente números.</span>'
        '<input id="cpf" name="cpf" type="text" inputmode="numeric" '
        f'autocomplete="username" aria-describedby="{cpf_described_by}"{invalid_state} required>'
        '<label for="password">Senha</label>'
        '<input id="password" name="password" type="password" '
        f'autocomplete="current-password" aria-describedby="{described_by}"{invalid_state} required>'
        '<button type="submit">Entrar</button>'
        "</form>"
    )
    return render_page(title="FAKE / SIMULAÇÃO", body=content, layout="card")
