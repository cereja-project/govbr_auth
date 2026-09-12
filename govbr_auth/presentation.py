"""Framework-neutral HTML presentation for local Gov.br simulations."""

from base64 import b64encode
from functools import lru_cache
from html import escape
from importlib.resources import files
from typing import Final, Literal, Protocol
from urllib.parse import urlsplit

from govbr_auth.core import GovBrUser
from govbr_auth.runtime_settings import GovBrProvider

DEMO_PAGE_PATH: Final[str] = "/govbr-auth-demo"

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
.brand-mark { color: #111827; flex: 0 0 auto; height: 3rem; width: 3rem; }
.site-header .brand-mark { color: #ffffff; }
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
<path d="M 41.78 17.51 C 42.43 17.38 43.23 17.49 43.76 17.64 C 44.30 17.78 44.80 18.06 45.25 18.38 C 45.70 18.70 55.44 28.06 56.14 29.03 C 56.85 30.00 57.46 31.09 57.75 32.25 C 58.05 33.41 57.99 35.06 57.88 35.84 C 57.76 36.61 57.49 37.37 57.13 38.07 C 56.78 38.77 56.21 39.52 55.65 40.17 C 55.09 40.82 43.10 52.25 42.15 52.92 C 41.20 53.60 39.77 54.29 39.06 54.53 C 38.34 54.77 37.49 54.87 36.83 54.90 C 36.17 54.94 35.48 54.88 34.85 54.78 C 34.22 54.68 33.58 54.53 32.99 54.29 C 32.40 54.05 31.45 53.55 30.76 53.05 C 30.08 52.54 25.91 48.57 25.81 48.34 C 25.71 48.12 25.71 47.83 25.81 47.60 C 25.91 47.37 31.31 42.11 31.50 42.03 C 31.70 41.95 31.93 41.95 32.12 42.03 C 32.31 42.11 34.02 44.29 34.60 44.50 C 35.18 44.72 35.89 44.63 36.46 44.38 C 37.02 44.13 44.33 36.84 44.50 36.58 C 44.68 36.32 44.81 36.02 44.88 35.71 C 44.94 35.41 44.96 34.59 44.88 34.23 C 44.79 33.87 44.60 33.54 44.38 33.24 C 44.16 32.94 41.59 30.39 41.29 30.27 C 40.98 30.14 40.60 30.15 40.30 30.27 C 39.99 30.38 39.58 30.95 39.43 31.01 C 39.27 31.07 39.09 31.07 38.93 31.01 C 38.78 30.95 33.44 25.63 33.36 25.44 C 33.28 25.25 33.28 25.01 33.36 24.82 C 33.44 24.63 38.72 19.28 39.43 18.75 C 40.14 18.23 41.13 17.65 41.78 17.51 Z" fill="currentColor"/>
<path d="M 25.07 9.10 C 25.92 8.99 27.07 9.01 28.04 9.22 C 29.01 9.42 30.02 9.79 30.89 10.33 C 31.75 10.88 36.99 15.96 37.08 16.15 C 37.16 16.34 37.16 16.58 37.08 16.77 C 37.00 16.96 31.00 22.91 30.89 22.96 C 30.77 23.01 30.63 23.01 30.51 22.96 C 30.40 22.92 28.43 20.65 27.91 20.49 C 27.40 20.32 26.79 20.49 26.30 20.73 C 25.82 20.98 18.73 27.99 18.38 28.78 C 18.03 29.58 17.98 30.56 18.26 31.38 C 18.54 32.20 20.75 34.37 20.98 34.60 C 21.21 34.83 21.46 35.10 21.72 35.22 C 21.99 35.34 22.31 35.42 22.59 35.34 C 22.87 35.27 23.55 34.53 23.70 34.48 C 23.86 34.42 24.05 34.41 24.20 34.48 C 24.35 34.54 29.09 39.40 29.15 39.55 C 29.21 39.71 29.22 39.90 29.15 40.05 C 29.09 40.20 23.61 45.64 23.09 45.99 C 22.56 46.34 21.80 46.64 21.35 46.73 C 20.91 46.82 20.43 46.83 19.99 46.73 C 19.55 46.63 18.34 46.13 17.64 45.62 C 16.93 45.11 8.50 36.37 7.86 35.47 C 7.22 34.56 6.68 33.56 6.37 32.50 C 6.06 31.43 5.93 29.92 6.00 28.90 C 6.07 27.89 6.35 26.87 6.74 25.93 C 7.14 24.99 7.72 24.13 8.35 23.33 C 8.99 22.53 19.84 11.73 20.49 11.20 C 21.14 10.67 21.83 10.19 22.59 9.84 C 23.35 9.49 24.21 9.20 25.07 9.10 Z" fill="currentColor"/>
<path d="M 28.04 24.70 C 28.26 24.68 28.82 24.76 29.15 24.94 C 29.49 25.13 39.41 34.95 39.55 35.34 C 39.69 35.73 39.61 36.21 39.43 36.58 C 39.25 36.95 35.65 40.39 35.22 40.54 C 34.79 40.69 34.27 40.61 33.86 40.42 C 33.44 40.22 23.74 30.40 23.58 30.02 C 23.42 29.64 23.42 29.16 23.58 28.78 C 23.74 28.40 27.23 25.07 27.42 24.94 C 27.60 24.82 27.82 24.71 28.04 24.70 Z" fill="#10b981"/>
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


def render_demo_page(
    *,
    provider: GovBrProvider,
    login_path: str,
    interactive: bool = False,
) -> str:
    """Render a provider-neutral authentication demonstration page."""
    action = (
        _render_demo_login_action(login_path)
        if interactive
        else render_primary_action(href=login_path, label="Entrar com GOV.BR")
    )
    if provider is GovBrProvider.FAKE:
        action += (
            '<form action="/govbr-auth-demo/debug" method="get">'
            '<button type="submit" role="switch" aria-checked="false" '
            'aria-label="Ativar modo debug">◉ Ativar modo debug</button>'
            '<p class="lead">Explore o fluxo por etapas, com animações e painel técnico.</p>'
            "</form>"
        )
        badge = render_simulation_badge()
        provider_copy = (
            "<strong>FakeGov</strong> simula o provedor somente para testes. "
            "Não use credenciais reais."
        )
        footer = "Ambiente de simulação. Não use credenciais reais."
    else:
        badge = ""
        provider_copy = (
            "<strong>Provedor oficial Gov.br</strong> configurado para esta aplicação."
        )
        footer = "Integração de autenticação Gov.br."
    return _render_demo_shell(
        badge=badge,
        provider_copy=provider_copy,
        action=action,
        interactive=interactive,
        login_path=login_path if interactive else None,
        footer=footer,
    )


def _render_demo_login_action(login_path: str) -> str:
    """Render the demo action with a hook for its native-window behavior."""
    _validate_internal_absolute_path(login_path)
    return (
        f'<a class="primary" data-govbr-login href="{escape(login_path, quote=True)}">'
        "Entrar com GOV.BR</a>"
    )


def _render_demo_shell(
    *,
    badge: str,
    provider_copy: str,
    action: str,
    interactive: bool,
    login_path: str | None,
    footer: str,
) -> str:
    """Wrap the provider demonstration content in the shared visual shell."""
    if interactive and login_path is None:
        raise ValueError("interactive demo requires a login path")
    success_panel = _render_demo_success_panel() if interactive else ""
    interaction_status = (
        '<p id="auth-status" class="message warning" role="status" '
        'aria-live="polite" hidden></p>'
        if interactive
        else ""
    )
    interaction_script = _render_demo_interaction_script() if interactive else ""
    home_id = ' id="demo-home"' if interactive else ""
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Demonstração de autenticação Gov.br</title>
<style>{responsive_css()}</style>
</head>
<body>
<header class="site-header"><div class="container brand-row">
{_render_brand_signature()}{badge}
</div></header>
<main class="container">
<section{home_id} class="hero" aria-labelledby="page-title">
<p class="eyebrow">Demonstração de autenticação</p>
<h1 id="page-title">Entrar com GOV.BR</h1>
<p class="lead">{provider_copy}</p>
{action}
</section>
{success_panel}
{interaction_status}
</main>
<footer class="site-footer"><div class="container">{footer}</div></footer>
{interaction_script}
</body>
</html>"""


def _render_demo_success_panel() -> str:
    """Render the safe success state shown by the opener window."""
    return (
        '<section id="demo-success" class="result" '
        'aria-labelledby="demo-success-title" hidden>'
        '<div class="success-mark" aria-hidden="true">✓</div>'
        '<h2 id="demo-success-title" tabindex="-1">Autenticação concluída</h2>'
        '<p class="message success" role="status">'
        "O callback foi validado com sucesso pelo backend.</p>"
        '<p class="lead">Nenhum token foi exposto ao navegador.</p>'
        f'{render_primary_action(href="/", label="Repetir o fluxo")}'
        "</section>"
    )


def _render_demo_interaction_script() -> str:
    """Render the opener-side bridge for the dedicated local demo."""
    return """<script>
(() => {
  const loginLink = document.querySelector("[data-govbr-login]");
  const home = document.getElementById("demo-home");
  const success = document.getElementById("demo-success");
  const status = document.getElementById("auth-status");
  const successTitle = document.getElementById("demo-success-title");
  let authWindow = null;

  if (!loginLink || !home || !success || !status || !successTitle) return;

  loginLink.addEventListener("click", (event) => {
    if (
      event.button !== 0 || event.metaKey || event.ctrlKey ||
      event.shiftKey || event.altKey
    ) return;
    event.preventDefault();
    authWindow = window.open(
      loginLink.href,
      "govbr-authentication",
      "popup,width=520,height=720,resizable=yes,scrollbars=yes"
    );
    if (!authWindow) {
      window.location.assign(loginLink.href);
      return;
    }
    status.hidden = false;
    status.textContent = "Conclua a autenticação na nova guia ou janela.";
    authWindow.focus();
  });

  window.addEventListener("message", (event) => {
    if (event.origin !== window.location.origin || event.source !== authWindow) return;
    if (!event.data || event.data.type !== "govbr-authentication-completed") return;
    if (authWindow && !authWindow.closed) authWindow.close();
    home.hidden = true;
    success.hidden = false;
    status.hidden = true;
    successTitle.focus();
  });
})();
</script>"""


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
            f'{render_primary_action(href="/auth/govbr/login", label="Entrar com GOV.BR")}'
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
    page = render_page(
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
            f'{render_primary_action(href="/", label="Repetir o fluxo")}'
            "</section>"
        ),
    )
    return page.replace(
        "</body>",
        (
            "<script>"
            "(() => {"
            "if (!window.opener || window.opener === window) return;"
            'window.opener.postMessage({ type: "govbr-authentication-completed" }, '
            "window.location.origin);"
            "window.setTimeout(() => window.close(), 100);"
            "})();"
            "</script></body>"
        ),
        1,
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
