import re
from typing import Literal, cast

import pytest

from govbr_auth.core import GovBrUser
from govbr_auth.fake.credentials import FakeLoginCredential
from govbr_auth.presentation import (
    DEMO_PAGE_PATH,
    render_error,
    render_demo_page,
    render_home,
    render_page,
    render_primary_action,
    render_safe_error_panel,
    render_simulation_badge,
    render_success,
    responsive_css,
)
from govbr_auth.runtime import GovBrProvider


def test_official_demo_page_has_neutral_copy_and_configured_login() -> None:
    page = render_demo_page(
        provider=GovBrProvider.OFFICIAL,
        login_path="/oauth/govbr/login",
    )

    assert DEMO_PAGE_PATH == "/govbr-auth-demo"
    assert 'href="/oauth/govbr/login"' in page
    assert ">Entrar com gov.br<" in page
    assert "Provedor oficial Gov.br" in page
    assert "SIMULAÇÃO" not in page
    assert "credenciais fictícias" not in page
    assert "ambiente local" not in page


def test_fake_demo_page_identifies_simulation_without_credentials() -> None:
    page = render_demo_page(
        provider=GovBrProvider.FAKE,
        login_path="/auth/govbr/login",
    )

    assert "FakeGov" in page
    assert "SIMULAÇÃO LOCAL" in page
    assert "Não use credenciais reais" in page
    for forbidden in (
        "12345678901",
        "ana-demo",
        "GOVBR_FAKE_CLIENT_SECRET",
        "access_token",
        "id_token",
    ):
        assert forbidden not in page


def test_shared_shell_preserves_accessibility_and_simulation_identity() -> None:
    page = render_page(title="Teste", body="<p>conteúdo</p>", layout="card")

    assert 'lang="pt-BR"' in page
    assert "SIMULAÇÃO LOCAL" in page
    assert ":focus-visible" in page
    assert "@media" in page


def test_shared_shell_uses_the_approved_brand_without_external_assets() -> None:
    page = render_page(title="Teste", body="<p>conteúdo</p>", layout="wide")

    assert "--brand-graphite: #111827;" in page
    assert "--brand-green: #10b981;" in page
    assert "--brand-red: #ef4444;" in page
    assert "--brand-wine: #991b1b;" in page
    assert 'font-family: "Inter", ui-sans-serif' in page
    assert 'font-family: "JetBrains Mono", ui-monospace' in page
    assert "@font-face" in page
    assert "url(data:font/woff2;base64," in page
    assert "<script" not in page
    assert "<link" not in page
    assert "url(http" not in page


def test_feedback_text_and_input_focus_meet_minimum_contrast() -> None:
    css = responsive_css()

    danger_text = _css_hex_token(css, "danger-text")
    danger_surface = _css_hex_token(css, "danger-surface")
    input_focus = _css_hex_token(css, "input-focus")
    input_surface = _css_hex_token(css, "surface")
    simulation_text = _css_hex_token(css, "simulation-text")
    simulation_surface = _css_hex_token(css, "simulation-surface")

    assert _contrast_ratio(danger_text, danger_surface) >= 4.5
    assert _contrast_ratio(input_focus, input_surface) >= 3
    assert _contrast_ratio(simulation_text, simulation_surface) >= 4.5
    assert "outline: .2rem solid var(--input-focus);" in css
    assert ".card-brand .simulation-badge {" in css


def test_wide_shell_identifies_the_project_instead_of_imitating_the_portal() -> None:
    page = render_page(title="Teste", body="<p>conteúdo</p>", layout="wide")

    assert 'class="brand-signature"' in page
    assert 'aria-label="govbr-auth"' in page
    assert 'class="brand-mark"' in page
    assert "<strong>Autenticamente</strong> pythônico." in page
    assert "SIMULAÇÃO LOCAL" in page


def test_shared_shell_escapes_title_but_accepts_owned_body_markup() -> None:
    page = render_page(
        title="<script>alert(1)</script>",
        body="<p>seguro</p>",
        layout="wide",
    )

    assert "<script>" not in page
    assert "<p>seguro</p>" in page


def test_shared_shell_rejects_unknown_layout() -> None:
    with pytest.raises(ValueError, match="layout must be 'wide' or 'card'"):
        render_page(
            title="Teste",
            body="<p>conteúdo</p>",
            layout=cast(object, "unknown"),
        )


def test_shared_presentation_components_escape_untrusted_values() -> None:
    action = render_primary_action(
        href="/auth/govbr/login",
        label="<Entrar>",
    )
    error = render_safe_error_panel(message="<erro>")

    assert 'href="/auth/govbr/login"' in action
    assert "&lt;Entrar&gt;" in action
    assert 'class="lead error-panel"' in error
    assert 'role="alert"' not in error
    assert "&lt;erro&gt;" in error


@pytest.mark.parametrize(
    "href",
    (
        "javascript:alert(1)",
        "https://example.test/login",
        "//example.test/login",
        "/auth/govbr/login?next=/callback",
        "/auth/govbr/login#callback",
    ),
)
def test_primary_action_rejects_non_path_or_executable_destinations(href: str) -> None:
    with pytest.raises(ValueError, match="internal absolute path"):
        render_primary_action(href=href, label="Entrar")


def test_card_layout_preserves_the_fake_provider_visual_contract() -> None:
    page = render_page(title="Teste", body="<p>conteúdo</p>", layout="card")

    assert '<body class="fake-flow card-layout">' in page
    assert '<main class="card-layout-main">' in page
    assert "body.card-layout {" in page
    assert "align-items: center;" in page
    assert "background: var(--canvas);" in page
    assert "display: flex;" in page
    assert "justify-content: center;" in page
    assert "main.card-layout-main {" in page
    assert "border-top: .25rem solid var(--brand-green);" in page
    assert "box-shadow: var(--shadow-lg);" in page
    assert "max-width: 32rem;" in page
    assert "@media (max-width: 36rem)" in page


@pytest.mark.parametrize(
    ("layout", "expected_body"),
    (
        ("wide", '<body class="fake-flow wide-layout">'),
        ("card", '<body class="fake-flow card-layout">'),
    ),
)
def test_every_fakegov_layout_uses_an_accessible_dark_color_scheme(
    layout: str, expected_body: str
) -> None:
    page = render_page(
        title="Teste",
        body="<p>conteúdo</p>",
        layout=cast(Literal["wide", "card"], layout),
    )
    flow_theme = _css_rule(page, "body.fake-flow")

    ink = _css_hex_token(flow_theme, "ink")
    muted = _css_hex_token(flow_theme, "muted")
    surface = _css_hex_token(flow_theme, "surface")
    canvas = _css_hex_token(flow_theme, "canvas")
    input_focus = _css_hex_token(flow_theme, "input-focus")
    emphasis = _css_hex_token(flow_theme, "emphasis")
    green_soft = _css_hex_token(flow_theme, "green-soft")
    code_text = _css_hex_token(flow_theme, "code-text")
    surface_soft = _css_hex_token(flow_theme, "surface-soft")
    success = _css_hex_token(flow_theme, "success")
    success_text = _css_hex_token(flow_theme, "success-text")

    assert expected_body in page
    assert '<meta name="color-scheme" content="dark">' in page
    assert "color-scheme: dark;" in flow_theme
    assert _contrast_ratio(ink, surface) >= 4.5
    assert _contrast_ratio(muted, surface) >= 4.5
    assert _contrast_ratio(input_focus, canvas) >= 3
    assert _contrast_ratio(surface, canvas) >= 1.15
    assert _contrast_ratio(emphasis, surface) >= 4.5
    assert _contrast_ratio(emphasis, green_soft) >= 4.5
    assert _contrast_ratio(code_text, surface_soft) >= 4.5
    assert code_text == emphasis
    assert _contrast_ratio(success_text, success) >= 3


def test_fakegov_flow_uses_flat_surfaces_without_gradients() -> None:
    page = render_page(title="Teste", body="<p>conteúdo</p>", layout="wide")

    assert "gradient(" not in page


def test_wide_layout_uses_only_the_header_dark_divider() -> None:
    page = render_page(title="Teste", body="<p>conteúdo</p>", layout="wide")

    header = _css_rule(page, ".site-header")
    hero = _css_rule(page, ".hero")
    login_card = _css_rule(page, "main.card-layout-main")

    assert "border-bottom: .25rem solid var(--line);" in header
    assert "border-top" not in hero
    assert "border-top: .25rem solid var(--brand-green);" in login_card


def test_fakegov_warning_uses_the_green_graphite_palette() -> None:
    page = render_page(title="Teste", body="<p>conteúdo</p>", layout="card")
    flow_theme = _css_rule(page, "body.fake-flow")

    ink = _css_hex_token(flow_theme, "ink")
    surface_soft = _css_hex_token(flow_theme, "surface-soft")
    warning = _css_hex_token(flow_theme, "warning")
    warning_surface = _css_hex_token(flow_theme, "warning-surface")

    assert warning == "#10b981"
    assert warning_surface == surface_soft
    assert _contrast_ratio(ink, warning_surface) >= 4.5
    assert _contrast_ratio(warning, warning_surface) >= 3


def test_shared_presentation_components_expose_simulation_and_responsive_theme() -> (
    None
):
    assert "SIMULAÇÃO LOCAL" in render_simulation_badge()
    assert "@media" in responsive_css()


def test_home_does_not_render_credentials_in_the_launcher_response() -> None:
    page = render_home(
        credentials=(
            FakeLoginCredential(
                cpf="12345678901",
                password="ana-demo",
                name="Ana Demo",
            ),
            FakeLoginCredential(
                cpf="98765432100",
                password="bruno-demo",
                name="Bruno Demo",
            ),
        )
    )

    assert "SIMULAÇÃO LOCAL" in page
    assert "Como funciona" in page
    assert "Credenciais da demo" in page
    assert "123.456.789-01" not in page
    assert "ana-demo" not in page
    assert "bruno-demo" not in page
    assert "nunca são exibidos" in page
    assert 'href="/auth/govbr/login"' in page
    assert ">Entrar com gov.br</a>" in page
    assert ":focus-visible" in page
    assert "@media" in page


def test_home_omits_credentials_for_external_repository() -> None:
    assert "Credenciais da demo" not in render_home(credentials=())


def test_success_masks_cpf_and_escapes_identity() -> None:
    user = GovBrUser(
        sub="12345678901",
        name="<b>Ana</b>",
        email="ana@example.test",
    )

    page = render_success(user)

    assert "***.***.***-01" in page
    assert "12345678901" not in page
    assert "<b>Ana</b>" not in page
    assert "ana@example.test" in page
    assert 'href="/auth/govbr/login"' in page
    assert "access_token" not in page
    assert "id_token" not in page


def test_result_pages_use_semantic_feedback_without_color_only_meaning() -> None:
    success = render_success(GovBrUser(sub="12345678901", name="Ana"))
    error = render_error(code="invalid_state", status_code=400)

    assert 'class="message success" role="status"' in success
    assert "Autenticação concluída" in success
    assert 'class="message danger" role="alert"' in error
    assert "Não foi possível autenticar" in error
    assert success.count('aria-live="polite"') + success.count('role="status"') == 1


def test_success_escapes_user_derived_values() -> None:
    user = GovBrUser(
        sub='<script>alert("subject")</script>',
        name='<img src=x onerror=alert("name")>',
        email="ana&demo@example.test",
    )

    page = render_success(user)

    assert '<script>alert("subject")</script>' not in page
    assert '<img src=x onerror=alert("name")>' not in page
    assert "ana&amp;demo@example.test" in page
    assert "&lt;img src=x onerror=alert(&quot;name&quot;)&gt;" in page


def test_error_uses_stable_code_without_internal_detail() -> None:
    page = render_error(code="invalid_state", status_code=400)

    assert "invalid_state" in page
    assert "Tente iniciar novamente" in page
    assert "traceback" not in page.casefold()


def test_error_replaces_unknown_code_that_could_contain_a_secret() -> None:
    secret = "access_token=secret-value"

    page = render_error(code=secret, status_code=502)

    assert "govbr_auth_error" in page
    assert secret not in page


@pytest.mark.parametrize(
    "code,status_code",
    (("invalid_callback", 400), ("internal_error", 500)),
    ids=("invalid-callback", "internal-error"),
)
def test_error_preserves_launcher_boundary_error_codes(
    code: str,
    status_code: int,
) -> None:
    page = render_error(code=code, status_code=status_code)

    assert code in page
    assert "govbr_auth_error" not in page


def _css_rule(css: str, selector: str) -> str:
    match = re.search(rf"{re.escape(selector)}\s*\{{(?P<body>[^}}]+)\}}", css)
    if match is None:
        raise AssertionError(f"CSS rule {selector} is missing")
    return match.group("body")


def _css_hex_token(css: str, name: str) -> str:
    match = re.search(rf"--{re.escape(name)}:\s*(#[0-9a-f]{{6}});", css)
    if match is None:
        raise AssertionError(f"CSS token --{name} is missing")
    return match.group(1)


def _contrast_ratio(first: str, second: str) -> float:
    lighter, darker = sorted(
        (_relative_luminance(first), _relative_luminance(second)), reverse=True
    )
    return (lighter + 0.05) / (darker + 0.05)


def _relative_luminance(color: str) -> float:
    channels = [int(color[index : index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [
        channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4
        for channel in channels
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]
