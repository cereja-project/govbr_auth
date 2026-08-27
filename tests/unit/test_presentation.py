import re
from typing import cast

import pytest

from govbr_auth.core import GovBrUser
from govbr_auth.fake.credentials import FakeLoginCredential
from govbr_auth.presentation import (
    render_error,
    render_home,
    render_page,
    render_primary_action,
    render_safe_error_panel,
    render_simulation_badge,
    render_success,
    responsive_css,
)


def test_shared_shell_preserves_accessibility_and_simulation_identity() -> None:
    page = render_page(title="Teste", body="<p>conteúdo</p>", layout="card")

    assert 'lang="pt-BR"' in page
    assert "SIMULAÇÃO LOCAL" in page
    assert ":focus-visible" in page
    assert "@media" in page


def test_shared_shell_uses_local_govbr_ds_foundations_without_external_assets() -> None:
    page = render_page(title="Teste", body="<p>conteúdo</p>", layout="wide")

    assert "--blue-warm-vivid-90: #071d41;" in page
    assert "--blue-warm-vivid-70: #1351b4;" in page
    assert "--gray-80: #333333;" in page
    assert 'font-family: Rawline, "Raleway",' in page
    assert "<script" not in page
    assert "<link" not in page
    assert "url(http" not in page


def test_feedback_text_and_input_focus_meet_minimum_contrast() -> None:
    css = responsive_css()

    danger_text = _css_hex_token(css, "danger-text")
    danger_surface = _css_hex_token(css, "red-vivid-10")
    input_focus = _css_hex_token(css, "input-focus")
    input_surface = _css_hex_token(css, "pure-0")

    assert _contrast_ratio(danger_text, danger_surface) >= 4.5
    assert _contrast_ratio(input_focus, input_surface) >= 3
    assert "outline: .2rem solid var(--input-focus);" in css


def test_wide_shell_identifies_the_project_instead_of_imitating_the_portal() -> None:
    page = render_page(title="Teste", body="<p>conteúdo</p>", layout="wide")

    assert '<span class="brand">govbr-auth</span>' in page
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

    assert '<body class="card-layout">' in page
    assert '<main class="card-layout-main">' in page
    assert "body.card-layout {" in page
    assert "align-items: center;" in page
    assert "background: var(--gray-2);" in page
    assert "display: flex;" in page
    assert "justify-content: center;" in page
    assert "main.card-layout-main {" in page
    assert "border-top: .25rem solid var(--warning);" in page
    assert "box-shadow: 0 0.5rem 1.5rem rgb(0 0 0 / 12%);" in page
    assert "max-width: 32rem;" in page
    assert "@media (max-width: 36rem)" in page


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
    assert ">Entrar com Gov.br</a>" in page
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
