import pytest

from govbr_auth.core import GovBrUser
from govbr_auth.demo import _html
from govbr_auth.demo._html import render_error, render_home, render_success


def test_home_renders_hybrid_showcase_and_default_credentials() -> None:
    page = render_home(
        credentials=(
            _html.DemoCredential(
                cpf="12345678901",
                password="ana-demo",
                name="Ana Demo",
            ),
            _html.DemoCredential(
                cpf="98765432100",
                password="bruno-demo",
                name="Bruno Demo",
            ),
        )
    )

    assert "SIMULAÇÃO LOCAL" in page
    assert "Como funciona" in page
    assert "123.456.789-01" in page and "ana-demo" in page
    assert 'href="/auth/govbr/login"' in page
    assert ":focus-visible" in page
    assert "@media" in page


def test_home_omits_credentials_for_external_repository() -> None:
    assert "Credenciais da demo" not in render_home(credentials=())


def test_home_constrains_credential_grid_item_for_narrow_viewports() -> None:
    page = render_home(
        credentials=(
            _html.DemoCredential(
                cpf="12345678901",
                password="ana-demo",
                name="Ana Demo",
            ),
        )
    )

    assert ".credentials { min-width: 0; }" in page


def test_home_provides_two_layer_visible_focus_indicator() -> None:
    page = render_home()

    focus_rule = page.split(":focus-visible", maxsplit=1)[1].split("}", maxsplit=1)[0]

    assert "outline:" in focus_rule
    assert "box-shadow:" in focus_rule


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
def test_error_preserves_demo_boundary_error_codes(
    code: str,
    status_code: int,
) -> None:
    page = render_error(code=code, status_code=status_code)

    assert code in page
    assert "govbr_auth_error" not in page
