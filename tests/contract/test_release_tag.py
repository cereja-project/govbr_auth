"""Execute the release version/tag gate without importing runtime dependencies."""

from pathlib import Path
import subprocess
import sys

import pytest

PROJECT_ROOT = Path(__file__).parents[2]
SCRIPT = PROJECT_ROOT / "scripts" / "verify_release_tag.py"


def _project(root: Path, *, dynamic: bool, version: str = "1.0.1") -> None:
    if dynamic:
        metadata = (
            '[project]\nname = "govbr-auth"\ndynamic = ["version"]\n'
            "[tool.setuptools.dynamic]\n"
            'version = {attr = "govbr_auth.__version__"}\n'
        )
        package = root / "govbr_auth"
        package.mkdir()
        (package / "__init__.py").write_text(
            'raise RuntimeError("package must not be imported")\n'
            f'__version__ = "{version}"\n',
            encoding="utf-8",
        )
    else:
        metadata = f'[project]\nname = "govbr-auth"\nversion = "{version}"\n'
    (root / "pyproject.toml").write_text(metadata, encoding="utf-8")


def _verify(root: Path, tag: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-S", str(SCRIPT), tag],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize("dynamic", (False, True))
def test_release_tag_accepts_matching_metadata_without_runtime_imports(
    tmp_path: Path, dynamic: bool
) -> None:
    _project(tmp_path, dynamic=dynamic)

    result = _verify(tmp_path, "v1.0.1")

    assert result.returncode == 0, result.stderr
    assert "v1.0.1" in result.stdout


@pytest.mark.parametrize("dynamic", (False, True))
@pytest.mark.parametrize("tag", ("v1.0.0", "v1.0.2", "1.0.1"))
def test_release_tag_rejects_mismatched_version_or_missing_prefix(
    tmp_path: Path, dynamic: bool, tag: str
) -> None:
    _project(tmp_path, dynamic=dynamic)

    result = _verify(tmp_path, tag)

    assert result.returncode == 1
    assert "v1.0.1" in result.stderr
    assert tag in result.stderr


def test_release_tag_rejects_nonliteral_dynamic_version(tmp_path: Path) -> None:
    _project(tmp_path, dynamic=True)
    (tmp_path / "govbr_auth" / "__init__.py").write_text(
        '__version__ = str("1.0.1")\n', encoding="utf-8"
    )

    result = _verify(tmp_path, "v1.0.1")

    assert result.returncode == 1
    assert "versão" in result.stderr.lower()


def test_release_tag_accepts_the_actual_dynamic_project() -> None:
    import govbr_auth

    result = _verify(PROJECT_ROOT, f"v{govbr_auth.__version__}")

    assert result.returncode == 0, result.stderr
