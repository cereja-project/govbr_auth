"""Verify that the published Sphinx tree resolves only supported APIs."""

import importlib
import re
from io import StringIO
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import dotenv_values

from examples.example_fastapi import settings_from_environment
from govbr_auth.core import ProviderEnvironment

DOCS_ROOT = Path(__file__).parents[2] / "docs"
PROJECT_ROOT = DOCS_ROOT.parent
TOCTREE_ENTRY = re.compile(r"^\s{3}([\w./-]+)\s*$", re.MULTILINE)
INCLUDE_DIRECTIVE = re.compile(r"^\.\. include::\s+(.+?)\s*$", re.MULTILINE)
AUTODOC_DIRECTIVE = re.compile(
    r"^\.\. auto(?:class|function|method|module)::\s+([\w.]+)\s*$",
    re.MULTILINE,
)


def _published_documents() -> set[Path]:
    published: set[Path] = set()
    pending = [DOCS_ROOT / "index.rst"]
    while pending:
        document = pending.pop()
        if document in published:
            continue
        published.add(document)
        source = document.read_text(encoding="utf-8")
        for target in TOCTREE_ENTRY.findall(source):
            child = (document.parent / target).with_suffix(".rst").resolve()
            assert child.is_file(), f"missing toctree document: {child}"
            pending.append(child)
        for target in INCLUDE_DIRECTIVE.findall(source):
            child = (document.parent / target).resolve()
            assert child.is_file(), f"missing included document: {child}"
    return published


def test_every_sphinx_document_is_published_and_resolvable() -> None:
    published = _published_documents()

    assert published == {path.resolve() for path in DOCS_ROOT.rglob("*.rst")}


def test_published_autodoc_references_are_importable() -> None:
    references = {
        reference
        for document in _published_documents()
        for reference in AUTODOC_DIRECTIVE.findall(document.read_text(encoding="utf-8"))
    }

    for reference in references:
        module_name, _, attribute_name = reference.rpartition(".")
        try:
            module = importlib.import_module(reference)
        except ModuleNotFoundError:
            module = importlib.import_module(module_name)
            assert hasattr(module, attribute_name), reference


def test_local_environment_example_configures_every_consumer_url_on_loopback(
    monkeypatch,
) -> None:
    example_source = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")
    local_assignments = "\n".join(
        line.removeprefix("# ")
        for line in example_source.splitlines()
        if line.startswith("# GOVBR_")
    )
    local_config = dotenv_values(stream=StringIO(local_assignments))
    assert set(local_config) == {
        "GOVBR_AUTHORIZATION_URL",
        "GOVBR_CLIENT_ID",
        "GOVBR_CLIENT_SECRET",
        "GOVBR_ENVIRONMENT",
        "GOVBR_ISSUER",
        "GOVBR_JWKS_URL",
        "GOVBR_REDIRECT_URI",
        "GOVBR_TOKEN_URL",
        "GOVBR_TRANSACTION_SECRET",
        "GOVBR_USERINFO_URL",
    }
    for name, value in local_config.items():
        assert value is not None
        monkeypatch.setenv(name, value)

    settings = settings_from_environment()

    assert settings.environment is ProviderEnvironment.LOCAL
    assert str(settings.redirect_uri) == "http://localhost/auth/govbr/callback"
    for url in (
        settings.authorization_url,
        settings.token_url,
        settings.userinfo_url,
        settings.issuer,
        settings.jwks_url,
    ):
        assert urlsplit(str(url)).hostname == "localhost"


def test_transaction_secret_documentation_explains_generation_and_storage() -> None:
    required_guidance = (
        "generate_transaction_secret()",
        "gere uma vez",
        "mantenha o valor secreto",
        "mesmo valor em todas as instâncias",
    )
    documented_sources = (
        (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8").lower(),
        (PROJECT_ROOT / "README.md").read_text(encoding="utf-8").lower(),
        (DOCS_ROOT / "guide" / "configuration.rst").read_text(encoding="utf-8").lower(),
    )

    documented_requirements = tuple(
        tuple(guidance in source for guidance in required_guidance)
        for source in documented_sources
    )

    assert documented_requirements == (
        (True, True, True, True),
        (True, True, True, True),
        (True, True, True, True),
    )


def test_installable_demo_command_is_consistent_across_entry_documents() -> None:
    required_commands = (
        'pip install "govbr-auth[demo]"',
        "python -m govbr_auth.demo",
        "http://localhost:8000",
    )
    sources = (
        (PROJECT_ROOT / "README.md").read_text(encoding="utf-8"),
        (DOCS_ROOT / "guide" / "quick-start.rst").read_text(encoding="utf-8"),
    )

    assert tuple(tuple(command in source for command in required_commands) for source in sources) == (
        (True, True, True),
        (True, True, True),
    )


def test_docs_distinguish_demo_fake_and_official_provider() -> None:
    source = (DOCS_ROOT / "guide" / "fake-mode.rst").read_text(encoding="utf-8")

    assert all(term in source for term in ("[demo]", "[fake]", "provedor oficial"))
