"""Pure HTML renderers for the local Gov.br authentication showcase."""

from dataclasses import dataclass
from html import escape

from govbr_auth.core import GovBrUser
from govbr_auth.presentation import (
    render_page,
    render_primary_action,
    render_safe_error_panel,
)

_ERROR_GUIDANCE = {
    "govbr_auth_error": "Não foi possível concluir a autenticação. Tente novamente mais tarde.",
    "invalid_state": "Tente iniciar novamente o fluxo de autenticação.",
    "expired_transaction": "Tente iniciar novamente o fluxo de autenticação.",
    "invalid_id_token": "Não foi possível validar a autenticação. Tente iniciar novamente.",
    "provider_rejected": "O Gov.br recusou a solicitação. Tente novamente mais tarde.",
    "provider_unavailable": "O Gov.br está indisponível no momento. Tente novamente mais tarde.",
    "invalid_callback": "O retorno da autenticação é inválido. Inicie novamente o fluxo.",
    "internal_error": "Ocorreu uma falha interna. Tente novamente mais tarde.",
}


@dataclass(frozen=True, slots=True)
class DemoCredential:
    """Represent one built-in credential disclosed by the demo UI."""

    cpf: str
    password: str
    name: str


def render_home(credentials: tuple[DemoCredential, ...] = ()) -> str:
    """Render the starting page for the local authentication showcase."""
    credentials_section = _render_credentials(credentials) if credentials else ""
    return _page(
        title="Showcase de autenticação Gov.br",
        body=(
            '<section class="hero" aria-labelledby="page-title">'
            '<p class="eyebrow">Integração Gov.br, do início ao callback</p>'
            '<h1 id="page-title">Teste a autenticação completa em ambiente local</h1>'
            '<p class="lead">Percorra uma simulação segura, isolada e sem acesso '
            "a serviços externos.</p>"
            f'{render_primary_action(href="/auth/govbr/login", label="Entrar com Gov.br")}'
            "</section>"
            '<section class="workflow" aria-labelledby="workflow-title">'
            '<p class="section-kicker">Como funciona</p>'
            '<h2 id="workflow-title">Um fluxo realista em três etapas</h2>'
            '<ol class="steps">'
            '<li><span aria-hidden="true">1</span><div><strong>Redirecione</strong>'
            "<p>A aplicação inicia o OAuth 2.0 com PKCE.</p></div></li>"
            '<li><span aria-hidden="true">2</span><div><strong>Autentique</strong>'
            "<p>O provedor local valida um CPF e uma senha fictícios.</p></div></li>"
            '<li><span aria-hidden="true">3</span><div><strong>Confira</strong>'
            "<p>O callback valida a identidade e exibe apenas dados seguros.</p></div></li>"
            "</ol></section>"
            f"{credentials_section}"
        ),
    )


def render_success(user: GovBrUser) -> str:
    """Render a successful fake authentication without exposing tokens or CPF."""
    name = escape(user.name or "Usuário de demonstração")
    email = escape(user.email or "não informado")
    masked_cpf = _mask_cpf(user.sub)
    return _page(
        title="Autenticação concluída",
        body=(
            '<section class="result" aria-live="polite" aria-labelledby="page-title">'
            '<div class="success-mark" aria-hidden="true">✓</div>'
            '<p class="eyebrow">Callback validado</p>'
            '<h1 id="page-title">Autenticação concluída</h1>'
            '<p class="lead">A identidade fictícia foi recebida com sucesso.</p>'
            '<dl class="identity">'
            f"<div><dt>Nome</dt><dd>{name}</dd></div>"
            f"<div><dt>CPF</dt><dd>{masked_cpf}</dd></div>"
            f"<div><dt>E-mail</dt><dd>{email}</dd></div>"
            "</dl>"
            f'{render_primary_action(href="/auth/govbr/login", label="Repetir o fluxo")}'
            "</section>"
        ),
    )


def render_error(*, code: str, status_code: int) -> str:
    """Render a safe error page from a stable public code only."""
    public_code = code if code in _ERROR_GUIDANCE else "govbr_auth_error"
    safe_code = escape(public_code)
    safe_status = escape(str(status_code))
    return _page(
        title="Não foi possível autenticar",
        body=(
            '<section class="result" role="alert" aria-labelledby="page-title">'
            '<div class="error-mark" aria-hidden="true">!</div>'
            '<p class="eyebrow">Fluxo interrompido</p>'
            '<h1 id="page-title">Não foi possível autenticar</h1>'
            f"{render_safe_error_panel(message=_ERROR_GUIDANCE[public_code])}"
            f'<p class="error-code">Código: <code>{safe_code}</code> '
            f"(HTTP {safe_status})</p>"
            f'{render_primary_action(href="/auth/govbr/login", label="Tentar novamente")}'
            "</section>"
        ),
    )


def _render_credentials(credentials: tuple[DemoCredential, ...]) -> str:
    rows = "".join(
        "<tr>"
        f'<th scope="row">{escape(credential.name)}</th>'
        f"<td><code>{_format_cpf(credential.cpf)}</code></td>"
        f"<td><code>{escape(credential.password)}</code></td>"
        "</tr>"
        for credential in credentials
    )
    return (
        '<section class="credentials" aria-labelledby="credentials-title">'
        '<p class="section-kicker">Pronto para testar</p>'
        '<h2 id="credentials-title">Credenciais da demo</h2>'
        "<p>Use somente estes dados fictícios no provedor local.</p>"
        '<div class="table-scroll"><table><thead><tr><th scope="col">Pessoa</th>'
        '<th scope="col">CPF</th><th scope="col">Senha</th></tr></thead>'
        f"<tbody>{rows}</tbody></table></div></section>"
    )


def _format_cpf(cpf: str) -> str:
    if len(cpf) != 11 or not cpf.isascii() or not cpf.isdigit():
        return escape(cpf)
    return f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}"


def _mask_cpf(cpf: str) -> str:
    suffix = (
        escape(cpf[-2:]) if len(cpf) == 11 and cpf.isascii() and cpf.isdigit() else "**"
    )
    return f"***.***.***-{suffix}"


def _page(*, title: str, body: str) -> str:
    return render_page(title=title, body=body, layout="wide")
