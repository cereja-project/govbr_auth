"""Render self-contained HTML pages for the local Fake Gov.br provider."""

import html

from govbr_auth.fake.models import FakeUser
from govbr_auth.fake.provider import FakeAuthorizationSession

_PAGE_STYLE = """
:root {
  color-scheme: light;
  font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  line-height: 1.5;
}
* { box-sizing: border-box; }
body {
  align-items: center;
  background: #f3f5f7;
  display: flex;
  justify-content: center;
  margin: 0;
  min-height: 100vh;
  padding: 1.5rem;
}
main {
  background: #fff;
  border-radius: 0.75rem;
  box-shadow: 0 0.5rem 1.5rem rgb(0 0 0 / 12%);
  max-width: 32rem;
  padding: 2rem;
  width: 100%;
}
h1 { font-size: 1.5rem; margin-top: 0; }
.warning {
  background: #fff4cc;
  border-left: 0.3rem solid #c58b00;
  padding: 0.75rem;
}
.error { color: #b3261e; font-weight: 700; }
form { display: grid; gap: 0.75rem; }
label { font-weight: 700; }
input {
  border: 1px solid #6c737f;
  border-radius: 0.35rem;
  font: inherit;
  padding: 0.75rem;
  width: 100%;
}
button {
  background: #1351b4;
  border: 0;
  border-radius: 0.35rem;
  color: #fff;
  cursor: pointer;
  font: inherit;
  font-weight: 700;
  padding: 0.75rem 1rem;
}
button + button { margin-top: 0.25rem; }
input:focus-visible, button:focus-visible {
  outline: 0.2rem solid #ffcd07;
  outline-offset: 0.15rem;
}
@media (max-width: 36rem) {
  body { padding: 0; }
  main { border-radius: 0; box-shadow: none; min-height: 100vh; padding: 1.25rem; }
}
""".strip()


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
    return _render_page(content)


def render_fake_user_selection(
    session: FakeAuthorizationSession,
    *,
    login_action: str,
) -> str:
    """Render the compatibility form for selecting a configured subject."""
    request_value = html.escape(session.request.get_secret_value(), quote=True)
    action_value = html.escape(login_action, quote=True)
    choices = "".join(_render_user_choice(user) for user in session.users)
    content = (
        "<h1>FAKE / SIMULAÇÃO</h1>"
        '<p class="warning">Provedor local de teste. Não é o portal oficial.</p>'
        f'<form method="post" action="{action_value}">'
        f'<input type="hidden" name="request" value="{request_value}">'
        f"{choices}</form>"
    )
    return _render_page(content)


def _render_user_choice(user: FakeUser) -> str:
    subject = html.escape(user.sub, quote=True)
    label_value = user.name or user.preferred_username or user.sub
    label = html.escape(label_value, quote=True)
    return (
        f'<button type="submit" name="subject" value="{subject}">'
        f"{label} ({subject})</button>"
    )


def _render_page(content: str) -> str:
    return (
        "<!doctype html>"
        '<html lang="pt-BR"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        "<title>FAKE / SIMULAÇÃO</title>"
        f"<style>{_PAGE_STYLE}</style></head><body><main>{content}</main></body></html>"
    )
