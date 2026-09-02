"""Tests for installed-wheel verification profiles."""

from pathlib import Path
import re

import pytest

from scripts import verify_distribution


@pytest.fixture
def fastapi_distribution_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[str, dict[str, str]]:
    """Execute the real verification orchestration without installing a wheel."""
    wheel = tmp_path / "package.whl"
    readme = tmp_path / "README.md"
    guide = tmp_path / "quick-start.rst"
    wheel.write_text("fixture", encoding="utf-8")
    documented_surface = "\n".join(
        (
            "GOVBR_DEMO_PAGE",
            "/govbr-auth-demo",
            "GovBrApplicationSettings.from_environment()",
            "Entrar com gov.br",
        )
    )
    for path in (readme, guide):
        path.write_text(documented_surface, encoding="utf-8")

    monkeypatch.setattr(
        verify_distribution,
        "distribution_profiles",
        lambda: (
            verify_distribution.DistributionProfile(
                "fastapi",
                ("fastapi", "fake"),
            ),
        ),
    )
    monkeypatch.setattr(
        verify_distribution,
        "_markdown_quickstart",
        lambda _: "app = object()\n",
    )
    monkeypatch.setattr(
        verify_distribution,
        "_rst_quickstart",
        lambda *_: "app = object()\n",
    )
    monkeypatch.setattr(verify_distribution.venv.EnvBuilder, "create", lambda *_: None)
    monkeypatch.setattr(verify_distribution, "_python_path", lambda _: Path("python"))
    monkeypatch.setattr(verify_distribution, "_install_profile", lambda *_: None)
    observed: dict[str, object] = {}

    def record_run(command, *, cwd, env, check):
        del cwd, check
        observed["probe"] = Path(command[1]).read_text(encoding="utf-8")
        observed["environment"] = dict(env)

    monkeypatch.setattr(verify_distribution.subprocess, "run", record_run)
    monkeypatch.setenv("GOVBR_FAKE_END_TO_END", "true")

    verify_distribution.verify_distribution(wheel, readme, guide)

    return observed["probe"], observed["environment"]


def test_distribution_profiles_install_each_documented_extra_in_isolation() -> None:
    factory = getattr(verify_distribution, "distribution_profiles", None)
    assert factory is not None

    profiles = factory()

    assert tuple((profile.name, profile.extras) for profile in profiles) == (
        ("fastapi", ("fastapi", "fake")),
        ("django", ("django",)),
        ("flask", ("flask",)),
    )


def test_fastapi_distribution_probe_targets_provider_only_jwks(
    fastapi_distribution_execution: tuple[str, dict[str, str]],
) -> None:
    """The standalone FakeGov probe must use the root JWKS endpoint."""
    probe, _ = fastapi_distribution_execution

    assert 'client.get("/jwk")' in probe
    assert "/fake-govbr/jwk" not in probe


def test_fastapi_distribution_probe_opens_the_documented_demo_page(
    fastapi_distribution_execution: tuple[str, dict[str, str]],
) -> None:
    probe, _ = fastapi_distribution_execution

    assert 'client.get("/govbr-auth-demo")' in probe
    assert "Entrar com gov.br" in probe


def test_distribution_child_environment_removes_obsolete_fake_switch(
    fastapi_distribution_execution: tuple[str, dict[str, str]],
) -> None:
    """A stale parent setting must not reach installed-wheel subprocesses."""
    _, environment = fastapi_distribution_execution

    assert "GOVBR_FAKE_END_TO_END" not in environment
    assert environment.get("GOVBR_DEMO_PAGE") == "true"


@pytest.mark.parametrize("document_name", ("README.md", "quick-start.rst"))
def test_distribution_requires_the_demo_contract_in_each_packaged_guide(
    document_name: str,
) -> None:
    required_symbols = (
        "GOVBR_DEMO_PAGE",
        "/govbr-auth-demo",
        "GovBrApplicationSettings.from_environment()",
        "Entrar com gov.br",
    )
    complete_source = "\n".join(required_symbols)

    for missing_symbol in required_symbols:
        with pytest.raises(
            ValueError,
            match=rf"{re.escape(document_name)}.*{re.escape(missing_symbol)}",
        ):
            verify_distribution._validate_demo_documentation(
                complete_source.replace(missing_symbol, ""),
                document_name,
            )
