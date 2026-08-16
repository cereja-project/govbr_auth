import pytest

from govbr_auth.presentation import (
    render_page,
    render_primary_action,
    render_safe_error_panel,
    render_simulation_badge,
    responsive_css,
)


def test_shared_shell_preserves_accessibility_and_simulation_identity() -> None:
    page = render_page(title="Teste", body="<p>conteúdo</p>", layout="card")

    assert 'lang="pt-BR"' in page
    assert "SIMULAÇÃO LOCAL" in page
    assert ":focus-visible" in page
    assert "@media" in page


def test_shared_shell_escapes_title_but_accepts_owned_body_markup() -> None:
    page = render_page(
        title="<script>alert(1)</script>",
        body="<p>seguro</p>",
        layout="wide",
    )

    assert "<script>" not in page
    assert "<p>seguro</p>" in page


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
    assert "background: #f3f5f7;" in page
    assert "display: flex;" in page
    assert "justify-content: center;" in page
    assert "main.card-layout-main {" in page
    assert "border-radius: 0.75rem;" in page
    assert "box-shadow: 0 0.5rem 1.5rem rgb(0 0 0 / 12%);" in page
    assert "max-width: 32rem;" in page
    assert "@media (max-width: 36rem)" in page


def test_shared_presentation_components_expose_simulation_and_responsive_theme() -> (
    None
):
    assert "SIMULAÇÃO LOCAL" in render_simulation_badge()
    assert "@media" in responsive_css()
