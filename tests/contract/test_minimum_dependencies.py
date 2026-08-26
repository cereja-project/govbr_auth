"""Keep the tested minimum dependency set aligned with public metadata."""

from pathlib import Path
import tomllib

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
import yaml

PROJECT_ROOT = Path(__file__).parents[2]


def _public_requirements() -> list[Requirement]:
    with (PROJECT_ROOT / "pyproject.toml").open("rb") as stream:
        project = tomllib.load(stream)["project"]

    dependency_strings = list(project["dependencies"])
    for extra, requirements in project["optional-dependencies"].items():
        if extra != "dev":
            dependency_strings.extend(requirements)
    return [Requirement(value) for value in dependency_strings]


def _project_direct_lower_bounds() -> dict[str, str]:
    lower_bounds: dict[str, str] = {}
    for requirement in _public_requirements():
        matches = [
            specifier.version
            for specifier in requirement.specifier
            if specifier.operator == ">="
        ]
        assert len(matches) == 1, requirement
        name = canonicalize_name(requirement.name)
        if name in lower_bounds:
            assert lower_bounds[name] == matches[0], requirement
        lower_bounds[name] = matches[0]
    return lower_bounds


def _minimum_pins() -> dict[str, str]:
    requirements_file = PROJECT_ROOT / "requirements-min.txt"
    pins: dict[str, str] = {}
    for line in requirements_file.read_text(encoding="utf-8").splitlines():
        requirement = Requirement(line)
        specifiers = list(requirement.specifier)
        assert len(specifiers) == 1, requirement
        assert specifiers[0].operator == "==", requirement
        name = canonicalize_name(requirement.name)
        assert name not in pins, requirement
        pins[name] = specifiers[0].version
    return pins


def test_minimum_requirements_match_project_lower_bounds() -> None:
    assert _minimum_pins() == _project_direct_lower_bounds()


def test_ci_runs_the_full_suite_with_minimum_dependencies_on_python_3_11() -> None:
    workflow_path = PROJECT_ROOT / ".github" / "workflows" / "pythonpackage.yml"
    workflow = yaml.load(
        workflow_path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader
    )
    job = workflow["jobs"]["minimum-dependencies"]
    commands = "\n".join(step.get("run", "") for step in job["steps"])

    assert job["runs-on"] == "ubuntu-latest"
    setup_python = next(
        step
        for step in job["steps"]
        if step.get("uses", "").startswith("actions/setup-python@")
    )
    assert setup_python["with"]["python-version"] == "3.11"
    assert "python -m pip install --no-deps -e ." in commands
    assert "python -m pip install -r requirements-min.txt" in commands
    assert "python -m pip check" in commands
    assert "python -m pytest" in commands
