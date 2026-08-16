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
        href='"><script>alert(1)</script>',
        label="<Entrar>",
    )
    error = render_safe_error_panel(message="<erro>")

    assert "<script>" not in action
    assert "&lt;Entrar&gt;" in action
    assert 'class="lead error-panel"' in error
    assert 'role="alert"' not in error
    assert "&lt;erro&gt;" in error


def test_shared_presentation_components_expose_simulation_and_responsive_theme() -> (
    None
):
    assert "SIMULAÇÃO LOCAL" in render_simulation_badge()
    assert "@media" in responsive_css()
