"""Protect the release metadata and documentation build environment."""

import runpy
import re
import tomllib
from pathlib import Path

import yaml

import govbr_auth

PROJECT_ROOT = Path(__file__).parents[2]


def _load_docs_workflow() -> dict[str, object]:
    workflow_path = PROJECT_ROOT / ".github" / "workflows" / "docs.yml"
    return yaml.load(workflow_path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def _load_workflow(name: str) -> dict[str, object]:
    workflow_path = PROJECT_ROOT / ".github" / "workflows" / name
    return yaml.load(workflow_path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def test_release_version_is_consistent_across_package_and_documentation() -> None:
    with (PROJECT_ROOT / "pyproject.toml").open("rb") as pyproject_file:
        project_version = tomllib.load(pyproject_file)["project"]["version"]
    docs_config = runpy.run_path(str(PROJECT_ROOT / "docs" / "conf.py"))

    versions = (
        project_version,
        govbr_auth.__version__,
        govbr_auth.VERSION,
        docs_config["version"],
        docs_config["release"],
    )

    assert versions == (
        "1.0.0",
        "1.0.0",
        "1.0.0",
        "1.0",
        "1.0.0",
    )


def test_docs_configuration_does_not_prepend_the_source_checkout() -> None:
    source = (PROJECT_ROOT / "docs" / "conf.py").read_text(encoding="utf-8")

    assert "sys.path" not in source


def test_docs_ci_builds_against_the_installed_wheel_outside_the_checkout() -> None:
    workflow = _load_docs_workflow()
    sphinx_steps = [
        step
        for step in workflow["jobs"]["build"]["steps"]
        if "python -m sphinx" in step.get("run", "")
    ]

    assert len(sphinx_steps) == 2
    assert all(
        step.get("working-directory") == "${{ runner.temp }}" for step in sphinx_steps
    )


def test_docs_job_installs_every_documented_adapter_before_sphinx() -> None:
    workflow = _load_docs_workflow()
    steps = workflow["jobs"]["build"]["steps"]
    run_steps = [step for step in steps if "run" in step]

    build_index = next(
        index
        for index, step in enumerate(run_steps)
        if "python -m build" in step["run"].splitlines()
    )
    wheel_install_index = next(
        index
        for index, step in enumerate(run_steps)
        if any(
            line.strip().startswith("python -m pip install ")
            and "${wheel_path}[fake,django,flask]" in line
            for line in step["run"].splitlines()
        )
    )
    sphinx_indexes = [
        index
        for index, step in enumerate(run_steps)
        if any(
            line.strip().startswith("python -m sphinx ")
            for line in step["run"].splitlines()
        )
    ]

    assert build_index < wheel_install_index < min(sphinx_indexes)
    assert run_steps[wheel_install_index]["shell"] == "bash"
    assert len(sphinx_indexes) == 2


def test_ci_covers_supported_pythons_and_major_operating_systems() -> None:
    workflow = _load_workflow("pythonpackage.yml")
    matrix = workflow["jobs"]["test"]["strategy"]["matrix"]

    assert matrix["python-version"] == ["3.11", "3.12", "3.13", "3.14"]
    assert matrix["os"] == ["ubuntu-latest", "windows-latest", "macos-latest"]


def test_ci_does_not_duplicate_branch_and_pull_request_runs() -> None:
    workflow = _load_workflow("pythonpackage.yml")

    assert workflow["on"]["push"] == {"branches": ["main"]}
    assert workflow["on"]["pull_request"] == {}


def test_ci_enforces_formatting_coverage_and_distribution_validation() -> None:
    workflow = _load_workflow("pythonpackage.yml")
    jobs = workflow["jobs"]
    quality_commands = "\n".join(
        step.get("run", "") for step in jobs["quality"]["steps"]
    )
    package_commands = "\n".join(
        step.get("run", "") for step in jobs["package"]["steps"]
    )

    assert "black --check govbr_auth tests examples scripts" in quality_commands
    assert "--cov-fail-under=90" in quality_commands
    assert "python -m build" in package_commands
    assert "python -m twine check" in package_commands
    assert "python scripts/verify_distribution.py" in package_commands


def test_ci_exposes_one_stable_required_status_for_branch_protection() -> None:
    workflow = _load_workflow("pythonpackage.yml")
    required_job = workflow["jobs"]["required"]

    assert required_job["if"] == "${{ always() }}"
    assert required_job["needs"] == [
        "quality",
        "test",
        "minimum-dependencies",
        "package",
    ]
    step = required_job["steps"][0]
    assert step["env"] == {
        "QUALITY_RESULT": "${{ needs.quality.result }}",
        "TEST_RESULT": "${{ needs.test.result }}",
        "MINIMUM_RESULT": "${{ needs.minimum-dependencies.result }}",
        "PACKAGE_RESULT": "${{ needs.package.result }}",
    }
    assert all(
        f'test "${variable}" = "success"' in step["run"]
        for variable in (
            "QUALITY_RESULT",
            "TEST_RESULT",
            "MINIMUM_RESULT",
            "PACKAGE_RESULT",
        )
    )


def test_release_uses_oidc_trusted_publishing_without_static_credentials() -> None:
    workflow = _load_workflow("pythonpublish.yml")
    publish_job = workflow["jobs"]["publish"]
    serialized = (
        PROJECT_ROOT / ".github" / "workflows" / "pythonpublish.yml"
    ).read_text(encoding="utf-8")

    assert publish_job["permissions"] == {"id-token": "write"}
    assert publish_job["environment"]["name"] == "pypi"
    assert publish_job["needs"] == "verify-and-build"
    assert any(
        step.get("uses")
        == "pypa/gh-action-pypi-publish@dc37677b2e1c63e2034f94d8a5b11f265b73ba33"
        for step in publish_job["steps"]
    )
    assert "TWINE_USERNAME" not in serialized
    assert "TWINE_PASSWORD" not in serialized
    assert "PYPI_PASSWORD" not in serialized


def test_release_verifies_tag_main_commit_tests_and_built_wheel() -> None:
    workflow = _load_workflow("pythonpublish.yml")
    verify_job = workflow["jobs"]["verify-and-build"]
    commands = "\n".join(
        step.get("run", "") for step in verify_job["steps"] if "run" in step
    )

    assert "GITHUB_REF_NAME" in commands
    assert "git merge-base --is-ancestor" in commands
    assert "python -m pytest" in commands
    assert "--cov-fail-under=90" in commands
    assert "python scripts/verify_distribution.py" in commands
    assert "python -m twine check" in commands


def test_workflows_pin_third_party_actions_to_commit_shas() -> None:
    for workflow_path in (PROJECT_ROOT / ".github" / "workflows").glob("*.yml"):
        workflow = _load_workflow(workflow_path.name)
        uses = (
            step["uses"]
            for job in workflow.get("jobs", {}).values()
            for step in job.get("steps", [])
            if "uses" in step
        )
        assert all(
            re.search(r"@[0-9a-f]{40}$", action) for action in uses
        ), workflow_path
