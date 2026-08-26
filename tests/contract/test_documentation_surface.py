"""Verify that the published Sphinx tree resolves only supported APIs."""

import importlib
import re
from pathlib import Path

import pytest

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


def test_environment_example_documents_the_canonical_provider_switch() -> None:
    source = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")

    assert "GOVBR_PROVIDER=official" in source
    assert "GOVBR_PROVIDER=fake" in source
    assert "create_development_app" not in source
    assert "There is no fake-mode flag" not in source


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


def test_fake_launcher_commands_are_consistent_across_entry_documents() -> None:
    required_commands = (
        'pip install "govbr-auth[fake]"',
        "python -m govbr_auth.fake",
        "GOVBR_FAKE_END_TO_END=true python -m govbr_auth.fake",
        '$env:GOVBR_FAKE_END_TO_END = "true"',
        "http://localhost:8000",
    )
    sources = (
        (PROJECT_ROOT / "README.md").read_text(encoding="utf-8"),
        (DOCS_ROOT / "guide" / "quick-start.rst").read_text(encoding="utf-8"),
    )

    assert tuple(
        tuple(command in source for command in required_commands) for source in sources
    ) == (
        (True, True, True, True, True),
        (True, True, True, True, True),
    )


def test_fastapi_fake_quickstart_install_is_complete_for_uvicorn() -> None:
    required_guidance = (
        'pip install "govbr-auth[fastapi,fake]"',
        "uvicorn myapp:app --reload",
        "http://127.0.0.1:8000/auth/govbr/login",
    )
    sources = (
        (PROJECT_ROOT / "README.md").read_text(encoding="utf-8"),
        (DOCS_ROOT / "guide" / "quick-start.rst").read_text(encoding="utf-8"),
    )

    assert tuple(
        tuple(guidance in source for guidance in required_guidance)
        for source in sources
    ) == (
        (True, True, True),
        (True, True, True),
    )


def test_entry_docs_describe_fakegov_as_provider_facade_with_canonical_public_names() -> (
    None
):
    sources = (
        (PROJECT_ROOT / "README.md").read_text(encoding="utf-8"),
        (DOCS_ROOT / "guide" / "quick-start.rst").read_text(encoding="utf-8"),
        (DOCS_ROOT / "api" / "fastapi.rst").read_text(encoding="utf-8"),
        (DOCS_ROOT / "api" / "django.rst").read_text(encoding="utf-8"),
        (DOCS_ROOT / "api" / "flask.rst").read_text(encoding="utf-8"),
    )
    combined = re.sub(r"\s+", " ", "\n".join(sources))

    assert "FakeGovSimulator" in combined
    assert "create_fake_gov_simulator" in combined
    assert "FakeGovBrRuntime" not in combined
    assert "create_fake_govbr_runtime" not in combined
    assert "mesmo runtime consumidor" in combined
    assert (
        "troca apenas os endpoints do provedor e o transporte HTTP interno" in combined
    )
    assert "FakeGovHttpTransport" in combined
    assert "transporte ASGI em memória" not in combined
    assert "ASGI in-memory transport" not in combined


def test_fastapi_api_doc_describes_the_fakegov_provider_facade_surface() -> None:
    source = re.sub(
        r"\s+",
        " ",
        (DOCS_ROOT / "api" / "fastapi.rst").read_text(encoding="utf-8"),
    )

    assert "FakeGovSimulator" in source
    assert "create_fake_gov_simulator" in source
    assert "FakeGovBrRuntime" not in source
    assert "create_fake_govbr_runtime" not in source
    assert "mesmo runtime consumidor" in source
    assert "troca apenas os endpoints do provedor e o transporte HTTP interno" in source


def test_fake_mode_guide_documents_the_supported_installation_matrix() -> None:
    source = (DOCS_ROOT / "guide" / "fake-mode.rst").read_text(encoding="utf-8")

    assert 'pip install "govbr-auth[fastapi,fake]"' in source
    assert 'pip install "govbr-auth[django]"' in source
    assert 'pip install "govbr-auth[flask]"' in source
    assert 'pip install "govbr-auth[fake]"' not in source


def test_installable_fake_command_is_an_exact_line_in_every_instruction() -> None:
    sources = (
        (PROJECT_ROOT / "README.md").read_text(encoding="utf-8"),
        (DOCS_ROOT / "guide" / "quick-start.rst").read_text(encoding="utf-8"),
        (DOCS_ROOT / "guide" / "troubleshooting.rst").read_text(encoding="utf-8"),
    )

    assert tuple(
        any(
            'pip install "govbr-auth[fake]"' == line.strip()
            for line in source.splitlines()
        )
        for source in sources
    ) == (
        True,
        True,
        True,
    )


def test_docs_explain_both_fake_intents_and_official_provider() -> None:
    source = (DOCS_ROOT / "guide" / "fake-mode.rst").read_text(encoding="utf-8")

    assert all(
        term in source
        for term in (
            "Usar FakeGov no meu app",
            "Executar end-to-end",
            "Uso avançado",
            "provedor oficial",
        )
    )


@pytest.mark.parametrize(
    "document",
    (
        PROJECT_ROOT / "README.md",
        DOCS_ROOT / "guide" / "quick-start.rst",
        DOCS_ROOT / "guide" / "fake-mode.rst",
    ),
    ids=("readme", "quick-start", "fake-mode"),
)
def test_fake_credentials_journey_is_documented_in_every_entry_guide(
    document: Path,
) -> None:
    required_guidance = (
        "GOVBR_FAKE_USERS_FILE",
        "fake-users.local.json",
        '"users"',
        '"cpf": "11122233344"',
        '"password": "senha-ficticia"',
        'export GOVBR_FAKE_USERS_FILE="$PWD/fake-users.local.json"',
        '$env:GOVBR_FAKE_USERS_FILE = "$PWD\\fake-users.local.json"',
        "não use credenciais reais",
        "python -m govbr_auth.fake",
    )

    source = document.read_text(encoding="utf-8")

    assert tuple(guidance in source for guidance in required_guidance) == (
        True,
        True,
        True,
        True,
        True,
        True,
        True,
        True,
        True,
    )


def test_user_docs_use_only_the_canonical_framework_adapter_surfaces() -> None:
    source = "\n".join(
        document.read_text(encoding="utf-8")
        for document in _published_documents() | {PROJECT_ROOT / "README.md"}
    )

    assert "from govbr_auth.fastapi import AuthContext, GovBrAuth" in source
    assert "from govbr_auth.django import GovBrAuth" in source
    assert "from govbr_auth.flask import GovBrAuth" in source
    assert "GOVBR_PROVIDER=fake" in source
    assert "app.include_router(auth.router)" in source
    assert "urlpatterns = auth.urlpatterns" in source
    assert "auth.register(app)" in source
    assert "python -m django runserver" in source
    assert "flask --app examples.example_flask:create_app run" in source
    assert "[demo]" not in source
    assert "govbr_auth.demo" not in source
    assert ".install(" not in source
    assert "from govbr_auth import AuthContext, GovBrAuth" not in source


def test_entry_docs_use_explicit_local_credentials_not_built_in_defaults() -> (
    None
):
    sources = (
        (PROJECT_ROOT / "README.md").read_text(encoding="utf-8"),
        (DOCS_ROOT / "guide" / "quick-start.rst").read_text(encoding="utf-8"),
    )

    assert tuple("GOVBR_FAKE_USERS_FILE" in source for source in sources) == (
        True,
        True,
    )
    assert tuple("11122233344" in source for source in sources) == (
        True,
        True,
    )
    assert tuple("senha-ficticia" in source for source in sources) == (
        True,
        True,
    )
    assert tuple("12345678901" in source for source in sources) == (
        False,
        False,
    )
    assert tuple("ana-demo" in source for source in sources) == (
        False,
        False,
    )
    assert tuple("bruno-demo" in source for source in sources) == (
        False,
        False,
    )


def test_advanced_fakegov_docs_match_application_argument_contract() -> None:
    source = "\n".join(
        (
            (DOCS_ROOT / "api" / "fake-govbr.rst").read_text(encoding="utf-8"),
            (DOCS_ROOT / "guide" / "fake-mode.rst").read_text(encoding="utf-8"),
        )
    )
    normalized = re.sub(r"\s+", " ", source)

    assert (
        "create_fake_govbr_router(runtime, *, prefix=None, application=None, "
        "credential_authenticator=None, automatic_subject=None, clock=utc_now)"
        in normalized
    )
    assert (
        "create_fake_govbr_app(runtime, *, application=None, "
        "credential_authenticator=None, automatic_subject=None, clock=utc_now)"
        in normalized
    )
    assert "FakeGovHttpApplication" in normalized
    assert "runtime.http_application" in normalized
