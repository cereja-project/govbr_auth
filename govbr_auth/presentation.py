"""Framework-neutral HTML presentation for local Gov.br simulations."""

from base64 import b64encode
from functools import lru_cache
from html import escape
from importlib.resources import files
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
  --brand-graphite: #111827;
  --brand-green: #10b981;
  --brand-red: #ef4444;
  --brand-wine: #991b1b;
  --ink: #0f172a;
  --muted: #64748b;
  --surface: #ffffff;
  --canvas: #f8fafc;
  --surface-soft: #f1f5f9;
  --green-soft: #d1fae5;
  --emphasis: #047857;
  --code-text: #047857;
  --line: #e2e8f0;
  --primary: var(--brand-green);
  --primary-dark: #059669;
  --success: #047857;
  --success-text: #ffffff;
  --success-surface: #ecfdf5;
  --simulation-text: #047857;
  --simulation-surface: #ecfdf5;
  --danger: var(--brand-wine);
  --danger-text: #991b1b;
  --danger-surface: #fef2f2;
  --input-focus: #047857;
  --warning: #b45309;
  --warning-surface: #fffbeb;
  --radius: 1rem;
  --shadow-sm: 0 1px 2px rgb(15 23 42 / 6%);
  --shadow-lg: 0 1.25rem 3rem rgb(15 23 42 / 14%);
  color-scheme: light;
  font-family: "Inter", ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont,
    "Segoe UI", sans-serif;
  line-height: 1.5;
}
* { box-sizing: border-box; }
body {
  background: var(--canvas);
  color: var(--ink); margin: 0; min-height: 100vh;
}
.container { margin-inline: auto; max-width: 70rem; padding-inline: 1.5rem; }
.site-header {
  background: var(--brand-graphite); border-bottom: .25rem solid var(--line);
  color: #f8fafc;
}
.brand-row { align-items: center; display: flex; gap: 1.5rem; justify-content: space-between; min-height: 5.5rem; }
.brand-signature { align-items: center; color: inherit; display: inline-flex; gap: .8rem; text-decoration: none; }
.brand-mark { flex: 0 0 auto; height: 3rem; width: 3rem; }
.brand-name { font-size: 1.25rem; font-weight: 800; letter-spacing: -.035em; }
.brand-name span { color: #94a3b8; font-weight: 300; }
.brand-tagline { color: #cbd5e1; font-size: .82rem; margin: .15rem 0 0; }
.brand-tagline strong { color: #f8fafc; }
.simulation-badge {
  background: rgb(16 185 129 / 12%); border: 1px solid rgb(16 185 129 / 55%);
  border-radius: 100em; color: #6ee7b7; font-size: .7rem; font-weight: 800;
  letter-spacing: .12em; padding: .4rem .75rem;
}
main.container { display: grid; gap: 1.5rem; padding-block: 3.5rem; }
section {
  background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius);
  box-shadow: var(--shadow-sm); padding: 2rem;
}
.hero {
  background: var(--surface);
  padding-block: 3.5rem;
}
.eyebrow, .section-kicker {
  color: var(--emphasis); font-size: .76rem; font-weight: 800; letter-spacing: .15em;
  margin: 0 0 .6rem; text-transform: uppercase;
}
h1 { font-size: clamp(2rem, 5vw, 3.6rem); letter-spacing: -.045em; line-height: 1.08; margin: 0; max-width: 15ch; }
h2 { font-size: clamp(1.45rem, 3vw, 2rem); letter-spacing: -.025em; margin: 0 0 1rem; }
.lead { color: var(--muted); font-size: 1.12rem; max-width: 58ch; }
.primary, button {
  background: var(--primary); border: 0; border-radius: .65rem; color: var(--brand-graphite); cursor: pointer;
  display: inline-block; font: inherit; font-weight: 750; margin-top: .8rem; padding: .85rem 1.15rem;
  text-decoration: none; transition: background-color .18s ease, box-shadow .18s ease, transform .18s ease;
}
.primary:hover, button:hover { background: var(--primary-dark); box-shadow: 0 .5rem 1rem rgb(5 150 105 / 18%); transform: translateY(-1px); }
:focus-visible {
  box-shadow: 0 0 0 .38rem rgb(16 185 129 / 28%);
  outline: .16rem solid var(--input-focus);
  outline-offset: .1rem;
}
.steps { display: grid; gap: 1rem; grid-template-columns: repeat(3, 1fr); list-style: none; margin: 1.5rem 0 0; padding: 0; }
.steps li { border-top: .2rem solid var(--primary); display: flex; gap: .8rem; padding-top: 1rem; }
.steps span {
  align-items: center; background: var(--green-soft); border-radius: 50%; color: var(--emphasis);
  display: inline-flex; flex: 0 0 2rem; font-weight: 800; height: 2rem; justify-content: center;
}
.steps p { color: var(--muted); margin: .35rem 0 0; }
.credentials { min-width: 0; }
.table-scroll { overflow-x: auto; }
table { border-collapse: collapse; min-width: 34rem; width: 100%; }
th, td { border-bottom: 1px solid var(--line); padding: .85rem; text-align: left; }
thead th { color: var(--muted); font-size: .8rem; text-transform: uppercase; }
code {
  background: var(--surface-soft); border-radius: .35rem; color: var(--code-text);
  font-family: "JetBrains Mono", ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: .88em; padding: .15rem .35rem;
}
.result { margin-inline: auto; max-width: 44rem; width: 100%; }
.success-mark, .error-mark {
  align-items: center; border-radius: 50%; display: flex; font-size: 1.5rem;
  font-weight: 900; height: 3rem; justify-content: center; margin-bottom: 1.25rem; width: 3rem;
}
.success-mark { background: var(--success); color: var(--success-text); }
.error-mark { background: var(--danger); color: #fff; }
.identity { border-top: 1px solid var(--line); margin-block: 1.5rem; }
.identity div { border-bottom: 1px solid var(--line); display: grid; gap: 1rem; grid-template-columns: 8rem 1fr; padding-block: .8rem; }
.identity dt { color: var(--muted); font-weight: 700; }
.identity dd { margin: 0; overflow-wrap: anywhere; }
.error-code { color: var(--muted); }
.site-footer { color: var(--muted); font-size: .88rem; padding-block: 0 2rem; text-align: center; }
body.fake-flow {
  --ink: #f8fafc;
  --muted: #cbd5e1;
  --surface: #1e293b;
  --canvas: #111827;
  --surface-soft: #0f172a;
  --line: #475569;
  --green-soft: #064e3b;
  --emphasis: #a7f3d0;
  --code-text: #a7f3d0;
  --simulation-text: #a7f3d0;
  --simulation-surface: #064e3b;
  --danger-text: #fca5a5;
  --danger-surface: #450a0a;
  --warning: #10b981;
  --warning-surface: #0f172a;
  --success: #6ee7b7;
  --success-text: #111827;
  --success-surface: #022c22;
  --input-focus: #10b981;
  background: var(--canvas); color-scheme: dark;
}
body.card-layout {
  align-items: center; display: flex; justify-content: center;
  margin: 0; min-height: 100vh; padding: 1.5rem;
}
main.card-layout-main {
  background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius);
  border-top: .25rem solid var(--brand-green); box-shadow: var(--shadow-lg);
  max-width: 32rem; padding: 2rem; width: 100%;
}
.card-brand { align-items: center; display: flex; justify-content: space-between; margin-bottom: 2rem; }
.card-brand .brand-mark { height: 2.75rem; width: 2.75rem; }
.card-brand .simulation-badge {
  background: var(--simulation-surface); border-color: #10b981; color: var(--simulation-text);
}
.card-layout-main h1 { font-size: 1.5rem; max-width: none; }
.message { border-left: .25rem solid; margin-block: 1rem; padding: 1rem; }
.message strong { display: block; margin-bottom: .25rem; }
.message.warning { background: var(--warning-surface); border-color: var(--warning); }
.message.danger { background: var(--danger-surface); border-color: var(--danger); }
.message.success { background: var(--success-surface); border-color: var(--success); }
.error { color: var(--danger-text); font-weight: 700; }
.card-layout-main form { display: grid; gap: .75rem; }
.card-layout-main label { font-weight: 700; }
.field-hint { color: var(--muted); font-size: .875rem; margin-top: -.5rem; }
.card-layout-main input {
  background: var(--surface-soft); border: 1px solid #64748b; border-radius: .5rem;
  color: var(--ink); font: inherit; min-height: 3rem; padding: .75rem; width: 100%;
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
  box-shadow: none; outline: .2rem solid var(--input-focus); outline-offset: .15rem;
}
@media (max-width: 44rem) {
  .container { padding-inline: 1rem; }
  main.container { padding-block: 1rem 2rem; }
  section, .hero { padding: 1.35rem; }
  .steps { grid-template-columns: 1fr; }
  .identity div { gap: .25rem; grid-template-columns: 1fr; }
  .brand-tagline { display: none; }
}
@media (max-width: 36rem) {
  body.card-layout { padding: 0; }
  main.card-layout-main { border-radius: 0; box-shadow: none; min-height: 100vh; padding: 1.25rem; }
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { scroll-behavior: auto !important; transition-duration: .01ms !important; }
}
""".strip()


@lru_cache(maxsize=1)
def _font_face_css() -> str:
    font_root = files("govbr_auth").joinpath("_assets", "fonts")

    def data_url(filename: str) -> str:
        payload = b64encode(font_root.joinpath(filename).read_bytes()).decode("ascii")
        return f"data:font/woff2;base64,{payload}"

    return "\n".join(
        (
            '@font-face { font-family: "Inter"; font-style: normal; font-weight: 100 900; '
            f'src: url({data_url("InterVariable.woff2")}) format("woff2"); font-display: swap; }}',
            '@font-face { font-family: "JetBrains Mono"; font-style: normal; font-weight: 400; '
            f'src: url({data_url("JetBrainsMono-Regular.woff2")}) format("woff2"); font-display: swap; }}',
            '@font-face { font-family: "JetBrains Mono"; font-style: normal; font-weight: 700; '
            f'src: url({data_url("JetBrainsMono-Bold.woff2")}) format("woff2"); font-display: swap; }}',
        )
    )


@lru_cache(maxsize=1)
def responsive_css() -> str:
    """Return the responsive rules used by every rendered local page."""
    return f"{_font_face_css()}\n{_THEME_CSS}"


def _render_brand_mark() -> str:
    return """<svg class="brand-mark" viewBox="0 0 64 64" role="img" aria-label="govbr-auth">
<g fill="none" stroke="#10b981" stroke-width="4" stroke-linejoin="round">
<path d="M 32 10 V 22 L 22 32 V 38"/><path d="M 32 22 L 42 32 V 38"/>
</g><g fill="#10b981"><circle cx="32" cy="10" r="3.5"/><circle cx="32" cy="22" r="3.5"/>
<circle cx="22" cy="38" r="2.5"/><circle cx="42" cy="38" r="2.5"/></g>
<circle cx="26" cy="46" r="11" fill="#ef4444"/><circle cx="38" cy="46" r="11" fill="#991b1b"/>
</svg>"""


def _render_brand_signature() -> str:
    return (
        '<div class="brand-signature">'
        f"{_render_brand_mark()}"
        '<div><div class="brand-name">govbr<span>-auth</span></div>'
        '<p class="brand-tagline"><strong>Autenticamente</strong> pythônico.</p></div>'
        "</div>"
    )


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
        page_body = f"""<body class="fake-flow wide-layout">
<header class="site-header"><div class="container brand-row">
{_render_brand_signature()}{render_simulation_badge()}
</div></header>
<main class="container">{body}</main>
<footer class="site-footer"><div class="container">
Ambiente local para desenvolvimento e testes. Não use credenciais reais.
</div></footer>
</body>"""
    elif layout == "card":
        page_body = f"""<body class="fake-flow card-layout">
<main class="card-layout-main"><div class="card-brand">{_render_brand_mark()}{render_simulation_badge()}</div>{body}</main>
</body>"""
    else:
        raise ValueError("layout must be 'wide' or 'card'")

    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="dark">
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
