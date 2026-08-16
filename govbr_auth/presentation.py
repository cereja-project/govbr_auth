"""Framework-neutral HTML presentation for local Gov.br simulations."""

from html import escape
from typing import Literal
from urllib.parse import urlsplit

_THEME_CSS = """
:root {
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
  color-scheme: light;
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont,
    "Segoe UI", sans-serif;
  line-height: 1.5;
}
* { box-sizing: border-box; }
body { background: var(--canvas); color: var(--ink); margin: 0; min-height: 100vh; }
.container { margin-inline: auto; max-width: 70rem; padding-inline: 1.5rem; }
.site-header { background: #071d41; color: #fff; }
.brand-row { align-items: center; display: flex; justify-content: space-between; min-height: 4.5rem; }
.brand { font-size: 1.15rem; font-weight: 800; letter-spacing: -.02em; }
.simulation-badge {
  background: var(--accent); border-radius: 999px; color: #302800; font-size: .72rem;
  font-weight: 800; letter-spacing: .08em; padding: .35rem .7rem;
}
main.container { display: grid; gap: 1.5rem; padding-block: 3rem; }
section { background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius); padding: 2rem; }
.hero { background: linear-gradient(135deg, #fff 55%, #e8f1ff); padding-block: 3rem; }
.eyebrow, .section-kicker {
  color: var(--primary); font-size: .78rem; font-weight: 800; letter-spacing: .09em;
  margin: 0 0 .6rem; text-transform: uppercase;
}
h1 { font-size: clamp(2rem, 5vw, 3.6rem); letter-spacing: -.045em; line-height: 1.08; margin: 0; max-width: 15ch; }
h2 { font-size: clamp(1.45rem, 3vw, 2rem); letter-spacing: -.025em; margin: 0 0 1rem; }
.lead { color: var(--muted); font-size: 1.12rem; max-width: 58ch; }
.primary, button {
  background: var(--primary); border: 0; border-radius: .55rem; color: #fff; cursor: pointer;
  display: inline-block; font: inherit; font-weight: 750; margin-top: .8rem; padding: .85rem 1.15rem;
  text-decoration: none; transition: background-color .18s ease, transform .18s ease;
}
.primary:hover, button:hover { background: var(--primary-dark); transform: translateY(-1px); }
:focus-visible {
  box-shadow: 0 0 0 .38rem #071d41;
  outline: .16rem solid #fff;
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
  align-items: center; background: #f3f5f7; display: flex; justify-content: center;
  margin: 0; min-height: 100vh; padding: 1.5rem;
}
main.card-layout-main {
  background: #fff; border-radius: 0.75rem; box-shadow: 0 0.5rem 1.5rem rgb(0 0 0 / 12%);
  max-width: 32rem; padding: 2rem; width: 100%;
}
.card-layout-main h1 { font-size: 1.5rem; max-width: none; }
.warning { background: #fff4cc; border-left: .3rem solid #c58b00; padding: .75rem; }
.error { color: var(--danger); font-weight: 700; }
.card-layout-main form { display: grid; gap: .75rem; }
.card-layout-main label { font-weight: 700; }
.card-layout-main input {
  border: 1px solid #6c737f; border-radius: .35rem; font: inherit; padding: .75rem; width: 100%;
}
.card-layout-main button {
  border-radius: .35rem; font-weight: 700; margin-top: 0; padding: .75rem 1rem;
}
.card-layout-main button + button { margin-top: .25rem; }
.card-layout-main input:focus-visible, .card-layout-main button:focus-visible {
  box-shadow: none; outline: .2rem solid #ffcd07; outline-offset: .15rem;
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
<span class="brand">gov.br auth</span>{render_simulation_badge()}
</div></header>
<main class="container">{body}</main>
<footer class="site-footer"><div class="container">
Ambiente local para desenvolvimento e testes. Não use credenciais reais.
</div></footer>
</body>"""
    else:
        page_body = f"""<body class="card-layout">
<main class="card-layout-main">{render_simulation_badge()}{body}</main>
</body>"""

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
