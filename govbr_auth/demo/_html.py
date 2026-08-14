"""Pure HTML renderers for the local Gov.br authentication showcase."""

from dataclasses import dataclass
from html import escape

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
            '<a class="primary" href="/auth/govbr/login">Iniciar autenticação</a>'
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
            '<a class="primary" href="/auth/govbr/login">Repetir o fluxo</a>'
            "</section>"
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
            '<section class="result" role="alert" aria-labelledby="page-title">'
            '<div class="error-mark" aria-hidden="true">!</div>'
            '<p class="eyebrow">Fluxo interrompido</p>'
            '<h1 id="page-title">Não foi possível autenticar</h1>'
            f'<p class="lead">{guidance}</p>'
            f'<p class="error-code">Código: <code>{safe_code}</code> '
            f"(HTTP {safe_status})</p>"
            '<a class="primary" href="/auth/govbr/login">Tentar novamente</a>'
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
    """Wrap content in the self-contained, accessible demo shell."""
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light">
<title>{escape(title)}</title>
<style>
:root {{
  --ink: #17213b;
  --muted: #536078;
  --surface: #ffffff;
  --canvas: #eef3f8;
  --primary: #1351b4;
  --primary-dark: #0c3d8f;
  --accent: #ffcd07;
  --line: #d9e2ec;
  --success: #168821;
  --danger: #b3261e;
  --radius: 1rem;
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont,
    "Segoe UI", sans-serif;
  line-height: 1.5;
}}
* {{ box-sizing: border-box; }}
body {{ background: var(--canvas); color: var(--ink); margin: 0; min-height: 100vh; }}
.container {{ margin-inline: auto; max-width: 70rem; padding-inline: 1.5rem; }}
.site-header {{ background: #071d41; color: #fff; }}
.brand-row {{ align-items: center; display: flex; justify-content: space-between; min-height: 4.5rem; }}
.brand {{ font-size: 1.15rem; font-weight: 800; letter-spacing: -.02em; }}
.simulation-badge {{
  background: var(--accent); border-radius: 999px; color: #302800; font-size: .72rem;
  font-weight: 800; letter-spacing: .08em; padding: .35rem .7rem;
}}
main.container {{ display: grid; gap: 1.5rem; padding-block: 3rem; }}
section {{ background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius); padding: 2rem; }}
.hero {{ background: linear-gradient(135deg, #fff 55%, #e8f1ff); padding-block: 3rem; }}
.eyebrow, .section-kicker {{
  color: var(--primary); font-size: .78rem; font-weight: 800; letter-spacing: .09em;
  margin: 0 0 .6rem; text-transform: uppercase;
}}
h1 {{ font-size: clamp(2rem, 5vw, 3.6rem); letter-spacing: -.045em; line-height: 1.08; margin: 0; max-width: 15ch; }}
h2 {{ font-size: clamp(1.45rem, 3vw, 2rem); letter-spacing: -.025em; margin: 0 0 1rem; }}
.lead {{ color: var(--muted); font-size: 1.12rem; max-width: 58ch; }}
.primary {{
  background: var(--primary); border-radius: .55rem; color: #fff; display: inline-block;
  font-weight: 750; margin-top: .8rem; padding: .85rem 1.15rem; text-decoration: none;
  transition: background-color .18s ease, transform .18s ease;
}}
.primary:hover {{ background: var(--primary-dark); transform: translateY(-1px); }}
:focus-visible {{
  box-shadow: 0 0 0 .38rem #071d41;
  outline: .16rem solid #fff;
  outline-offset: .1rem;
}}
.steps {{ display: grid; gap: 1rem; grid-template-columns: repeat(3, 1fr); list-style: none; margin: 1.5rem 0 0; padding: 0; }}
.steps li {{ border-top: .2rem solid var(--primary); display: flex; gap: .8rem; padding-top: 1rem; }}
.steps span {{
  align-items: center; background: #e8f1ff; border-radius: 50%; color: var(--primary);
  display: inline-flex; flex: 0 0 2rem; font-weight: 800; height: 2rem;
  justify-content: center;
}}
.steps p {{ color: var(--muted); margin: .35rem 0 0; }}
.table-scroll {{ overflow-x: auto; }}
table {{ border-collapse: collapse; min-width: 34rem; width: 100%; }}
th, td {{ border-bottom: 1px solid var(--line); padding: .85rem; text-align: left; }}
thead th {{ color: var(--muted); font-size: .8rem; text-transform: uppercase; }}
code {{ background: #edf2f7; border-radius: .3rem; color: var(--ink); padding: .15rem .35rem; }}
.result {{ margin-inline: auto; max-width: 44rem; width: 100%; }}
.success-mark, .error-mark {{
  align-items: center; border-radius: 50%; color: #fff; display: flex; font-size: 1.5rem;
  font-weight: 900; height: 3rem; justify-content: center; margin-bottom: 1.25rem;
  width: 3rem;
}}
.success-mark {{ background: var(--success); }}
.error-mark {{ background: var(--danger); }}
.identity {{ border-top: 1px solid var(--line); margin-block: 1.5rem; }}
.identity div {{
  border-bottom: 1px solid var(--line); display: grid; gap: 1rem;
  grid-template-columns: 8rem 1fr; padding-block: .8rem;
}}
.identity dt {{ color: var(--muted); font-weight: 700; }}
.identity dd {{ margin: 0; overflow-wrap: anywhere; }}
.error-code {{ color: var(--muted); }}
.site-footer {{ color: var(--muted); font-size: .88rem; padding-block: 0 2rem; text-align: center; }}
@media (max-width: 44rem) {{
  .container {{ padding-inline: 1rem; }}
  main.container {{ padding-block: 1rem 2rem; }}
  section, .hero {{ padding: 1.35rem; }}
  .steps {{ grid-template-columns: 1fr; }}
  .identity div {{ gap: .25rem; grid-template-columns: 1fr; }}
}}
@media (prefers-reduced-motion: reduce) {{
  *, *::before, *::after {{ scroll-behavior: auto !important; transition-duration: .01ms !important; }}
}}
</style>
</head>
<body>
<header class="site-header"><div class="container brand-row">
<span class="brand">gov.br auth</span><span class="simulation-badge">SIMULAÇÃO LOCAL</span>
</div></header>
<main class="container">{body}</main>
<footer class="site-footer"><div class="container">
Ambiente local para desenvolvimento e testes. Não use credenciais reais.
</div></footer>
</body>
</html>"""
