"""Framework-neutral HTML presentation for local Gov.br simulations."""

from html import escape
from typing import Literal, Protocol
from urllib.parse import urlsplit

from govbr_auth.core import GovBrUser

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


class PresentedCredential(Protocol):
    """Describe the safe demonstrative fields accepted by the launcher home."""

    cpf: str
    password: str
    name: str


_THEME_CSS = """
:root {
  --pure-0: #ffffff;
  --gray-2: #f8f8f8;
  --gray-20: #cccccc;
  --gray-40: #888888;
  --gray-80: #333333;
  --blue-warm-vivid-90: #071d41;
  --blue-warm-vivid-80: #0c326f;
  --blue-warm-vivid-70: #1351b4;
  --blue-warm-vivid-10: #e8f1ff;
  --green-cool-vivid-50: #168821;
  --green-cool-vivid-5: #e3f5e1;
  --yellow-vivid-20: #ffcd07;
  --yellow-vivid-5: #fff5c2;
  --red-vivid-50: #e52207;
  --red-vivid-10: #f9dede;
  --ink: var(--gray-80);
  --muted: #555555;
  --surface: var(--pure-0);
  --canvas: var(--gray-2);
  --primary: var(--blue-warm-vivid-70);
  --primary-dark: var(--blue-warm-vivid-80);
  --accent: var(--yellow-vivid-20);
  --line: var(--gray-20);
  --success: var(--green-cool-vivid-50);
  --danger: var(--red-vivid-50);
  --danger-text: #b3261e;
  --input-focus: #1351b4;
  --warning: #c58b00;
  --radius: .5rem;
  color-scheme: light;
  font-family: Rawline, "Raleway", ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont,
    "Segoe UI", sans-serif;
  line-height: 1.5;
}
* { box-sizing: border-box; }
body { background: var(--canvas); color: var(--ink); margin: 0; min-height: 100vh; }
.container { margin-inline: auto; max-width: 70rem; padding-inline: 1.5rem; }
.site-header { background: var(--blue-warm-vivid-90); color: var(--pure-0); }
.brand-row { align-items: center; display: flex; justify-content: space-between; min-height: 4.5rem; }
.brand { font-size: 1.15rem; font-weight: 800; letter-spacing: -.02em; }
.simulation-badge {
  background: var(--accent); border-radius: 100em; color: #302800; font-size: .72rem;
  font-weight: 800; letter-spacing: .08em; padding: .35rem .7rem;
}
main.container { display: grid; gap: 1.5rem; padding-block: 3rem; }
section { background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius); padding: 2rem; }
.hero { background: linear-gradient(135deg, var(--pure-0) 55%, var(--blue-warm-vivid-10)); padding-block: 3rem; }
.eyebrow, .section-kicker {
  color: var(--primary); font-size: .78rem; font-weight: 800; letter-spacing: .09em;
  margin: 0 0 .6rem; text-transform: uppercase;
}
h1 { font-size: clamp(2rem, 5vw, 3.6rem); letter-spacing: -.045em; line-height: 1.08; margin: 0; max-width: 15ch; }
h2 { font-size: clamp(1.45rem, 3vw, 2rem); letter-spacing: -.025em; margin: 0 0 1rem; }
.lead { color: var(--muted); font-size: 1.12rem; max-width: 58ch; }
.primary, button {
  background: var(--primary); border: 0; border-radius: 100em; color: var(--pure-0); cursor: pointer;
  display: inline-block; font: inherit; font-weight: 750; margin-top: .8rem; padding: .85rem 1.15rem;
  text-decoration: none; transition: background-color .18s ease, transform .18s ease;
}
.primary:hover, button:hover { background: var(--primary-dark); transform: translateY(-1px); }
:focus-visible {
  box-shadow: 0 0 0 .38rem var(--blue-warm-vivid-90);
  outline: .16rem solid var(--pure-0);
  outline-offset: .1rem;
}
.steps { display: grid; gap: 1rem; grid-template-columns: repeat(3, 1fr); list-style: none; margin: 1.5rem 0 0; padding: 0; }
.steps li { border-top: .2rem solid var(--primary); display: flex; gap: .8rem; padding-top: 1rem; }
.steps span {
  align-items: center; background: #e8f1ff; border-radius: 50%; color: var(--primary);
  display: inline-flex; flex: 0 0 2rem; font-weight: 800; height: 2rem; justify-content: center;
}
.steps p { color: var(--muted); margin: .35rem 0 0; }
.credentials { min-width: 0; }
.table-scroll { overflow-x: auto; }
table { border-collapse: collapse; min-width: 34rem; width: 100%; }
th, td { border-bottom: 1px solid var(--line); padding: .85rem; text-align: left; }
thead th { color: var(--muted); font-size: .8rem; text-transform: uppercase; }
code { background: #edf2f7; border-radius: .3rem; color: var(--ink); padding: .15rem .35rem; }
.result { margin-inline: auto; max-width: 44rem; width: 100%; }
.success-mark, .error-mark {
  align-items: center; border-radius: 50%; color: #fff; display: flex; font-size: 1.5rem;
  font-weight: 900; height: 3rem; justify-content: center; margin-bottom: 1.25rem; width: 3rem;
}
.success-mark { background: var(--success); }
.error-mark { background: var(--danger); }
.identity { border-top: 1px solid var(--line); margin-block: 1.5rem; }
.identity div { border-bottom: 1px solid var(--line); display: grid; gap: 1rem; grid-template-columns: 8rem 1fr; padding-block: .8rem; }
.identity dt { color: var(--muted); font-weight: 700; }
.identity dd { margin: 0; overflow-wrap: anywhere; }
.error-code { color: var(--muted); }
.site-footer { color: var(--muted); font-size: .88rem; padding-block: 0 2rem; text-align: center; }
body.card-layout {
  align-items: center; background: var(--gray-2); display: flex; justify-content: center;
  margin: 0; min-height: 100vh; padding: 1.5rem;
}
main.card-layout-main {
  background: var(--pure-0); border-radius: 0.75rem; border-top: .25rem solid var(--warning);
  box-shadow: 0 0.5rem 1.5rem rgb(0 0 0 / 12%);
  max-width: 32rem; padding: 2rem; width: 100%;
}
.card-layout-main h1 { font-size: 1.5rem; max-width: none; }
.message { border-left: .25rem solid; margin-block: 1rem; padding: 1rem; }
.message strong { display: block; margin-bottom: .25rem; }
.message.warning { background: var(--yellow-vivid-5); border-color: var(--warning); }
.message.danger { background: var(--red-vivid-10); border-color: var(--danger); }
.message.success { background: var(--green-cool-vivid-5); border-color: var(--success); }
.error { color: var(--danger-text); font-weight: 700; }
.card-layout-main form { display: grid; gap: .75rem; }
.card-layout-main label { font-weight: 700; }
.field-hint { color: var(--muted); font-size: .875rem; margin-top: -.5rem; }
.card-layout-main input {
  background: var(--pure-0); border: 1px solid var(--gray-40); border-radius: .25rem;
  color: var(--gray-80); font: inherit; min-height: 3rem; padding: .75rem; width: 100%;
}
.card-layout-main input[aria-invalid="true"] { border-color: var(--danger); border-width: 2px; }
.card-layout-main button {
  border-radius: .35rem; font-weight: 700; margin-top: 0; padding: .75rem 1rem;
}
.card-layout-main button + button { margin-top: .25rem; }
.card-layout-main input:focus-visible {
  box-shadow: none; outline: .2rem solid var(--input-focus); outline-offset: .15rem;
}
.card-layout-main button:focus-visible {
  box-shadow: none; outline: .2rem solid var(--yellow-vivid-20); outline-offset: .15rem;
}
@media (max-width: 44rem) {
  .container { padding-inline: 1rem; }
  main.container { padding-block: 1rem 2rem; }
  section, .hero { padding: 1.35rem; }
  .steps { grid-template-columns: 1fr; }
  .identity div { gap: .25rem; grid-template-columns: 1fr; }
}
@media (max-width: 36rem) {
  body.card-layout { padding: 0; }
  main.card-layout-main { border-radius: 0; box-shadow: none; min-height: 100vh; padding: 1.25rem; }
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { scroll-behavior: auto !important; transition-duration: .01ms !important; }
}
""".strip()


def responsive_css() -> str:
    """Return the responsive rules used by every rendered local page."""
    return _THEME_CSS


def render_simulation_badge() -> str:
    """Render the stable visual marker for local simulations."""
    return '<span class="simulation-badge">SIMULAÇÃO LOCAL</span>'


def render_primary_action(*, href: str, label: str) -> str:
    """Render a safely escaped primary action for an internal absolute path."""
    _validate_internal_absolute_path(href)
    return f'<a class="primary" href="{escape(href, quote=True)}">{escape(label)}</a>'


def _validate_internal_absolute_path(href: str) -> None:
    """Reject external, executable, and non-canonical action destinations."""
    try:
        parts = urlsplit(href)
    except ValueError as error:
        raise ValueError("href must be an internal absolute path") from error

    if (
        not href.startswith("/")
        or href.startswith("//")
        or "\\" in href
        or parts.scheme
        or parts.netloc
        or parts.query
        or parts.fragment
        or not parts.path
        or any(character.isspace() for character in href)
    ):
        raise ValueError("href must be an internal absolute path")


def render_safe_error_panel(*, message: str) -> str:
    """Render public error text without treating it as markup."""
    return f'<p class="lead error-panel">{escape(message)}</p>'


def render_page(*, title: str, body: str, layout: Literal["wide", "card"]) -> str:
    """Wrap owned HTML markup in the shared, accessible local shell."""
    if layout == "wide":
        page_body = f"""<body>
<header class="site-header"><div class="container brand-row">
<span class="brand">govbr-auth</span>{render_simulation_badge()}
</div></header>
<main class="container">{body}</main>
<footer class="site-footer"><div class="container">
Ambiente local para desenvolvimento e testes. Não use credenciais reais.
</div></footer>
</body>"""
    elif layout == "card":
        page_body = f"""<body class="card-layout">
<main class="card-layout-main">{render_simulation_badge()}{body}</main>
</body>"""
    else:
        raise ValueError("layout must be 'wide' or 'card'")

    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light">
<title>{escape(title)}</title>
<style>{responsive_css()}</style>
</head>
{page_body}
</html>"""


def render_home(credentials: tuple[PresentedCredential, ...] = ()) -> str:
    """Render the starting page for the complete local authentication flow."""
    credentials_section = _render_credentials(credentials) if credentials else ""
    return render_page(
        title="Showcase de autenticação Gov.br",
        layout="wide",
        body=(
            '<section class="hero" aria-labelledby="page-title">'
            '<p class="eyebrow">Integração Gov.br, do início ao callback</p>'
            '<h1 id="page-title">Teste a autenticação completa em ambiente local</h1>'
            '<p class="lead">Percorra uma simulação segura, isolada e sem acesso '
            "a serviços externos.</p>"
            f'{render_primary_action(href="/auth/govbr/login", label="Entrar com gov.br")}'
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
    return render_page(
        title="Autenticação concluída",
        layout="wide",
        body=(
            '<section class="result" aria-labelledby="page-title">'
            '<div class="success-mark" aria-hidden="true">✓</div>'
            '<h1 id="page-title">Autenticação concluída</h1>'
            '<div class="message success" role="status"><strong>Callback validado</strong>'
            "A identidade fictícia foi recebida com sucesso.</div>"
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
    return render_page(
        title="Não foi possível autenticar",
        layout="wide",
        body=(
            '<section class="result" aria-labelledby="page-title">'
            '<div class="error-mark" aria-hidden="true">!</div>'
            '<h1 id="page-title">Não foi possível autenticar</h1>'
            '<div class="message danger" role="alert"><strong>Fluxo interrompido</strong>'
            f"{render_safe_error_panel(message=_ERROR_GUIDANCE[public_code])}</div>"
            f'<p class="error-code">Código: <code>{safe_code}</code> '
            f"(HTTP {safe_status})</p>"
            f'{render_primary_action(href="/auth/govbr/login", label="Tentar novamente")}'
            "</section>"
        ),
    )


def _render_credentials(_credentials: tuple[PresentedCredential, ...]) -> str:
    """Explain the local credential boundary without rendering credential data."""
    return (
        '<section class="credentials" aria-labelledby="credentials-title">'
        '<p class="section-kicker">Pronto para testar</p>'
        '<h2 id="credentials-title">Credenciais da demo</h2>'
        "<p>Os dados de acesso são mantidos somente no runtime local e nunca são "
        "exibidos nesta resposta. Use apenas credenciais fictícias configuradas "
        "para o ambiente de desenvolvimento.</p>"
        "</section>"
    )


def _mask_cpf(cpf: str) -> str:
    suffix = (
        escape(cpf[-2:]) if len(cpf) == 11 and cpf.isascii() and cpf.isdigit() else "**"
    )
    return f"***.***.***-{suffix}"
