"""Contract tests for the framework-independent base distribution."""

from pathlib import Path
import tomllib

PROJECT_ROOT = Path(__file__).parents[2]


def _project_metadata() -> dict[str, object]:
    with (PROJECT_ROOT / "pyproject.toml").open("rb") as stream:
        return tomllib.load(stream)["project"]


def test_base_dependencies_do_not_include_web_frameworks() -> None:
    metadata = _project_metadata()
    dependencies = set(metadata.get("dependencies", []))
    optional_dependencies = set(metadata["optional-dependencies"])

    assert not any(
        dependency.lower().startswith(framework)
        for dependency in dependencies
        for framework in ("fastapi", "django", "flask")
    )
    assert {"fastapi", "django", "flask"} <= optional_dependencies
