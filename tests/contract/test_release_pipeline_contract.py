"""Protect the release metadata and documentation build environment."""

import runpy
import tomllib
from pathlib import Path

import yaml

import govbr_auth

PROJECT_ROOT = Path(__file__).parents[2]


def _load_docs_workflow() -> dict[str, object]:
    workflow_path = PROJECT_ROOT / ".github" / "workflows" / "docs.yml"
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
        "1.0.0rc1",
        "1.0.0rc1",
        "1.0.0rc1",
        "1.0",
        "1.0.0rc1",
    )


def test_docs_job_installs_built_demo_wheel_before_sphinx() -> None:
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
            and "${wheel_path}[demo]" in line
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
