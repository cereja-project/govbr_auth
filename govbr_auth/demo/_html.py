"""Pure HTML renderers for the local Gov.br authentication showcase."""

from html import escape

from govbr_auth.core import GovBrUser


_ERROR_GUIDANCE = {
    "govbr_auth_error": "Não foi possível concluir a autenticação. Tente novamente mais tarde.",
    "invalid_state": "Tente iniciar novamente o fluxo de autenticação.",
    "expired_transaction": "Tente iniciar novamente o fluxo de autenticação.",
    "invalid_id_token": "Não foi possível validar a autenticação. Tente iniciar novamente.",
    "provider_rejected": "O Gov.br recusou a solicitação. Tente novamente mais tarde.",
    "provider_unavailable": "O Gov.br está indisponível no momento. Tente novamente mais tarde.",
}


def render_home() -> str:
    """Render the starting page for the local authentication showcase."""
    return _page(
        title="Showcase de autenticação Gov.br",
        body=(
            "<p class=\"badge\">FAKE / SIMULAÇÃO</p>"
            "<h1>Teste o fluxo de autenticação Gov.br localmente</h1>"
            "<p>Execute o fluxo sem credenciais Gov.br nem serviços externos.</p>"
            "<ol><li>Redirecionar</li><li>Escolher usuário</li><li>Validar callback</li></ol>"
            '<a class="primary" href="/auth/govbr/login">Iniciar autenticação</a>'
        ),
    )


def render_success(user: GovBrUser) -> str:
    """Render a successful fake authentication without exposing tokens."""
    name = escape(user.name or "Usuário de demonstração")
    subject = escape(user.sub)
    email = escape(user.email or "não informado")
    return _page(
        title="Autenticação concluída",
        body=(
            "<h1>Autenticação concluída</h1>"
            f"<dl><dt>Nome</dt><dd>{name}</dd>"
            f"<dt>Subject</dt><dd>{subject}</dd>"
            f"<dt>E-mail</dt><dd>{email}</dd></dl>"
            '<a class="primary" href="/auth/govbr/login">Repetir o fluxo</a>'
        ),
    )


def render_error(*, code: str, status_code: int) -> str:
    """Render a safe error page from a stable public code only."""
    public_code = code if code in _ERROR_GUIDANCE else "govbr_auth_error"
    safe_code = escape(public_code)
    safe_status = escape(str(status_code))
    guidance = _ERROR_GUIDANCE[public_code]
    return _page(
        title="Não foi possível autenticar",
        body=(
            "<h1>Não foi possível autenticar</h1>"
            f"<p>{guidance}</p>"
            f"<p>Código: <code>{safe_code}</code> (HTTP {safe_status})</p>"
            '<a class="primary" href="/auth/govbr/login">Tentar novamente</a>'
        ),
    )


def _page(*, title: str, body: str) -> str:
    """Wrap a page body in the local showcase's self-contained HTML shell."""
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title>
<style>
body {{ background: #f5f7fb; color: #172033; font-family: sans-serif; margin: 0; }}
main {{ background: #fff; border-radius: 12px; box-shadow: 0 3px 15px #17203322; margin: 4rem auto; max-width: 42rem; padding: 2.5rem; }}
h1 {{ margin-top: 0; }}
.badge {{ color: #075985; font-weight: 700; }}
.primary {{ background: #075985; border-radius: 6px; color: #fff; display: inline-block; padding: .75rem 1rem; text-decoration: none; }}
dt {{ font-weight: 700; margin-top: .75rem; }}
dd {{ margin-left: 0; }}
</style>
</head>
<body><main>{body}</main></body>
</html>"""
