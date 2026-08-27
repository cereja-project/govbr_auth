"""Verify that the published Sphinx tree resolves only supported APIs."""

import importlib
import re
import runpy
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from govbr_auth.runtime_settings import _FAKE_FIELDS, _OFFICIAL_OAUTH_FIELDS

DOCS_ROOT = Path(__file__).parents[2] / "docs"
PROJECT_ROOT = DOCS_ROOT.parent
INCLUDE_DIRECTIVE = re.compile(r"^\.\. include::\s+(.+?)\s*$", re.MULTILINE)
AUTODOC_DIRECTIVE = re.compile(
    r"^\.\. auto(?:class|function|method|module)::\s+([\w.]+)\s*$",
    re.MULTILINE,
)
SVG_HEX_COLOR = re.compile(r"#[0-9a-f]{6}")
SVG_PAINT_REFERENCE = re.compile(r"url\(#[A-Za-z_][\w.-]*\)")
SVG_PAINT_PROPERTIES = {"fill", "stroke", "stop-color"}
GOVBR_DIAGRAM_COLORS = {
    "#071d41",
    "#0c326f",
    "#1351b4",
    "#333333",
    "#555555",
    "#888888",
    "#cccccc",
    "#e8f1ff",
    "#f8f8f8",
    "#fb923c",
    "#fff7ed",
    "#ffffff",
}


def _normalized_prose(source: str) -> str:
    return re.sub(r"\s+", " ", source.replace("`", "")).lower()


def _relative_luminance(color: str) -> float:
    channels = tuple(int(color[index : index + 2], 16) / 255 for index in (1, 3, 5))
    linear = tuple(
        channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4
        for channel in channels
    )
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast_ratio(first: str, second: str) -> float:
    lighter, darker = sorted(
        (_relative_luminance(first), _relative_luminance(second)), reverse=True
    )
    return (lighter + 0.05) / (darker + 0.05)


def _svg_paint_values(source: str) -> set[str]:
    root = ET.fromstring(source)
    values: set[str] = set()
    for element in root.iter():
        element_name = element.tag.rsplit("}", maxsplit=1)[-1].lower()
        assert element_name != "style", "SVG <style> elements are not supported"
        assert "style" not in element.attrib, "SVG style attributes are not supported"
        for name, value in element.attrib.items():
            property_name = name.rsplit("}", maxsplit=1)[-1]
            if property_name in SVG_PAINT_PROPERTIES:
                values.add(value.strip().lower())
    return values


def _assert_brand_svg_contract(source: str) -> None:
    assert "<?" not in source
    assert "<!doctype" not in source.lower()
    root = ET.fromstring(source)
    namespace = "{http://www.w3.org/2000/svg}"
    allowed_elements = {"svg", "title", "desc", "g", "path", "circle"}

    assert root.tag == f"{namespace}svg"
    assert root.attrib["role"] == "img"
    assert root.attrib["viewBox"]
    title = root.find(f"{namespace}title")
    description = root.find(f"{namespace}desc")
    assert title is not None
    assert description is not None
    labelled_ids = root.attrib["aria-labelledby"].split()
    identified_elements = {
        element.attrib["id"]: element
        for element in root.iter()
        if "id" in element.attrib
    }

    assert labelled_ids
    assert labelled_ids == [title.attrib["id"], description.attrib["id"]]
    assert all(
        identifier in identified_elements
        and (identified_elements[identifier].text or "").strip()
        for identifier in labelled_ids
    )
    assert all(
        element.tag.rsplit("}", maxsplit=1)[-1] in allowed_elements
        for element in root.iter()
    )
    assert root.find(f".//{namespace}text") is None
    assert not any(
        attribute.rsplit("}", maxsplit=1)[-1].lower().startswith("on")
        or attribute.rsplit("}", maxsplit=1)[-1].lower() in {"href", "style"}
        or "://" in value
        or value.strip().lower().startswith("url(")
        for element in root.iter()
        for attribute, value in element.attrib.items()
    )


def _toctree_entries(source: str) -> tuple[str, ...]:
    entries: list[str] = []
    lines = source.splitlines()
    index = 0
    while index < len(lines):
        if lines[index] != ".. toctree::":
            index += 1
            continue
        index += 1
        while index < len(lines):
            child_line = lines[index]
            if not child_line.strip() or child_line.startswith("   :"):
                index += 1
                continue
            if not child_line.startswith("   "):
                break
            entries.append(child_line.strip())
            index += 1
    return tuple(entries)


def _published_documents() -> set[Path]:
    published: set[Path] = set()
    pending = [DOCS_ROOT / "index.rst"]
    while pending:
        document = pending.pop()
        if document in published:
            continue
        published.add(document)
        source = document.read_text(encoding="utf-8")
        for target in _toctree_entries(source):
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


def test_environment_example_documents_every_supported_variable() -> None:
    source = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")
    documented_variables = set(
        re.findall(r"^#?\s*(GOVBR_[A-Z0-9_]+)=", source, re.MULTILINE)
    )
    supported_variables = {
        "GOVBR_PROVIDER",
        *_OFFICIAL_OAUTH_FIELDS,
        *_FAKE_FIELDS,
    }
    expected_variables = {
        "GOVBR_PROVIDER",
        "GOVBR_ENVIRONMENT",
        "GOVBR_AUTHORIZATION_URL",
        "GOVBR_TOKEN_URL",
        "GOVBR_USERINFO_URL",
        "GOVBR_CLIENT_ID",
        "GOVBR_CLIENT_SECRET",
        "GOVBR_REDIRECT_URI",
        "GOVBR_SCOPE",
        "GOVBR_TRANSACTION_SECRET",
        "GOVBR_ISSUER",
        "GOVBR_JWKS_URL",
        "GOVBR_CONNECT_TIMEOUT_SECONDS",
        "GOVBR_READ_TIMEOUT_SECONDS",
        "GOVBR_CLOCK_SKEW_SECONDS",
        "GOVBR_FAKE_END_TO_END",
        "GOVBR_FAKE_HOST",
        "GOVBR_FAKE_PORT",
        "GOVBR_FAKE_PROVIDER_PREFIX",
        "GOVBR_FAKE_CLIENT_ID",
        "GOVBR_FAKE_CLIENT_SECRET",
        "GOVBR_FAKE_REDIRECT_URI",
        "GOVBR_FAKE_REQUEST_TTL_SECONDS",
        "GOVBR_FAKE_AUTHORIZATION_CODE_TTL_SECONDS",
        "GOVBR_FAKE_ACCESS_TOKEN_TTL_SECONDS",
        "GOVBR_FAKE_ID_TOKEN_TTL_SECONDS",
        "GOVBR_FAKE_USERS_FILE",
    }

    assert supported_variables == expected_variables
    assert documented_variables == expected_variables


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


def test_entry_docs_highlight_stateless_multi_worker_deployments() -> None:
    sources = (
        _normalized_prose((PROJECT_ROOT / "README.md").read_text(encoding="utf-8")),
        _normalized_prose((DOCS_ROOT / "index.rst").read_text(encoding="utf-8")),
        _normalized_prose(
            (DOCS_ROOT / "guide" / "quick-start.rst").read_text(encoding="utf-8")
        ),
    )
    required_guidance = (
        "múltiplos workers",
        "sem armazenamento compartilhado",
        "mesma secret",
    )

    assert all(
        all(guidance in source for guidance in required_guidance) for source in sources
    )
    assert "uvicorn myapp:app --workers 4" in sources[0]
    assert "uvicorn myapp:app --workers 4" in sources[2]


def test_security_docs_describe_the_stateless_replay_boundary_exactly() -> None:
    sources = (
        _normalized_prose((PROJECT_ROOT / "README.md").read_text(encoding="utf-8")),
        _normalized_prose(
            (DOCS_ROOT / "guide" / "configuration.rst").read_text(encoding="utf-8")
        ),
        _normalized_prose(
            (DOCS_ROOT / "guide" / "troubleshooting.rst").read_text(encoding="utf-8")
        ),
    )
    required_guidance = (
        "fernet",
        "ttl",
        "pkce",
        "nonce",
        "authorization code de uso único",
        "state não é um registro de uso único",
    )

    assert all(
        all(guidance in source for guidance in required_guidance) for source in sources
    )


def test_user_docs_do_not_reference_the_removed_transaction_store() -> None:
    sources = "\n".join(
        document.read_text(encoding="utf-8") for document in _published_documents()
    )
    diagram = (DOCS_ROOT / "media" / "authentication-sequence.svg").read_text(
        encoding="utf-8"
    )

    assert "InMemoryTransactionStore" not in sources
    assert "TransactionStore" not in sources
    assert "transações mantidas em memória" not in sources
    assert "armazenados no backend" not in diagram
    assert "cifrados no state" in diagram


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
        "http://localhost:8000/auth/govbr/login",
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


def test_readme_leads_with_the_fakegov_value_and_visual_flow() -> None:
    source = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    sections = [line for line in source.splitlines() if line.startswith("## ")]
    assert sections[0] == "## Índice"
    assert sections[1] == "## Instalação"
    assert sections[2] == "## Teste a integração sem depender do gov.br"
    assert "docs/media/fakegov-flow.svg" in source
    assert "**FakeGov**" in source
    assert "Instalar" in source
    assert "Iniciar" in source
    assert "Entrar" in source
    assert "Concluir" in source


def test_entry_docs_quote_the_launcher_button_label_verbatim() -> None:
    sources = (
        (PROJECT_ROOT / "README.md").read_text(encoding="utf-8"),
        (DOCS_ROOT / "guide" / "quick-start.rst").read_text(encoding="utf-8"),
    )
    assert tuple("**Entrar com gov.br**" in source for source in sources) == (
        True,
        True,
    )
    assert tuple("Entrar com Gov.br" in source for source in sources) == (
        False,
        False,
    )


def test_communication_guide_uses_versioned_diagrams_instead_of_ascii_art() -> None:
    source = (DOCS_ROOT / "guide" / "communication-flow.rst").read_text(
        encoding="utf-8"
    )

    assert "../media/provider-switch.svg" in source
    assert "../media/authentication-sequence.svg" in source
    assert "Frontend       API + govbr-auth" not in source
    assert "Frontend       API FastAPI" not in source


@pytest.mark.parametrize(
    "filename",
    (
        "authentication-sequence.svg",
        "fakegov-flow.svg",
        "provider-switch.svg",
    ),
)
def test_versioned_diagrams_use_the_application_color_palette(filename: str) -> None:
    source = (DOCS_ROOT / "media" / filename).read_text(encoding="utf-8")
    paint_values = _svg_paint_values(source)
    colors = {value for value in paint_values if SVG_HEX_COLOR.fullmatch(value)}
    structural_values = paint_values - colors

    assert all(
        value == "none" or SVG_PAINT_REFERENCE.fullmatch(value)
        for value in structural_values
    )
    assert colors <= GOVBR_DIAGRAM_COLORS
    assert "#1351b4" in colors


@pytest.mark.parametrize(
    "filename",
    (
        "govbr-auth-logo.svg",
        "govbr-auth-logo-light.svg",
        "govbr-auth-logo-monochrome.svg",
        "govbr-auth-mark.svg",
    ),
)
def test_brand_assets_are_accessible_self_contained_svgs(filename: str) -> None:
    source = (DOCS_ROOT / "media" / filename).read_text(encoding="utf-8")
    _assert_brand_svg_contract(source)


@pytest.mark.parametrize(
    "filename",
    (
        "govbr-auth-logo.svg",
        "govbr-auth-logo-light.svg",
        "govbr-auth-logo-monochrome.svg",
    ),
)
def test_wordmark_cherries_align_with_the_letter_baseline(filename: str) -> None:
    source = (DOCS_ROOT / "media" / filename).read_text(encoding="utf-8")
    root = ET.fromstring(source)
    namespace = "{http://www.w3.org/2000/svg}"
    cherries = root.findall(f".//{namespace}circle")

    assert len(cherries) == 2
    assert all(
        float(cherry.attrib["cy"]) + float(cherry.attrib["r"]) <= 50
        for cherry in cherries
    )


@pytest.mark.parametrize(
    "prefix",
    (
        '<?xml-stylesheet type="text/css" href="https://evil.example/x.css"?>',
        '<!DOCTYPE svg SYSTEM "https://evil.example/ext.dtd">',
    ),
)
def test_brand_svg_contract_rejects_external_xml_prologs(prefix: str) -> None:
    source = (
        f"{prefix}"
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1" '
        'role="img" aria-labelledby="title desc">'
        '<title id="title">Marca</title>'
        '<desc id="desc">Descrição</desc>'
        '<path d="M0 0"/>'
        "</svg>"
    )

    with pytest.raises(AssertionError):
        _assert_brand_svg_contract(source)


def test_light_brand_colors_contrast_with_the_sphinx_header() -> None:
    source = (DOCS_ROOT / "media" / "govbr-auth-logo-light.svg").read_text(
        encoding="utf-8"
    )
    colors = {
        value
        for value in _svg_paint_values(source)
        if SVG_HEX_COLOR.fullmatch(value) and value != "#ffffff"
    }

    sphinx_config = runpy.run_path(str(DOCS_ROOT / "conf.py"))
    header_background = sphinx_config["html_theme_options"][
        "style_nav_header_background"
    ]

    assert colors
    assert all(_contrast_ratio(color, header_background) >= 3 for color in colors)


def test_documentation_entrypoints_publish_the_brand_assets() -> None:
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    sphinx_config = runpy.run_path(str(DOCS_ROOT / "conf.py"))

    assert (
        "https://raw.githubusercontent.com/cereja-project/govbr_auth/"
        "main/docs/media/govbr-auth-logo.svg"
    ) in readme
    assert sphinx_config["html_theme_options"]["logo_only"] is True
    assert sphinx_config["html_logo"] == "media/govbr-auth-logo-light.svg"
    assert sphinx_config["html_favicon"] == "media/govbr-auth-mark.svg"
    assert "_static" in sphinx_config["html_static_path"]
    assert "brand.css" in sphinx_config["html_css_files"]


def test_authentication_sequence_lifelines_have_graphical_contrast() -> None:
    source = (DOCS_ROOT / "media" / "authentication-sequence.svg").read_text(
        encoding="utf-8"
    )
    root = ET.fromstring(source)
    background = root.find("{http://www.w3.org/2000/svg}rect")
    lifelines = next(
        element
        for element in root.iter("{http://www.w3.org/2000/svg}g")
        if "stroke-dasharray" in element.attrib
    )

    assert background is not None
    assert _contrast_ratio(lifelines.attrib["stroke"], background.attrib["fill"]) >= 3


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
    assert "flask --app flask_app:app run" in source
    assert "examples.django_settings" not in source
    assert "examples.example_flask" not in source
    assert "[demo]" not in source
    assert "govbr_auth.demo" not in source
    assert ".install(" not in source
    assert "from govbr_auth import AuthContext, GovBrAuth" not in source


def test_entry_docs_use_explicit_local_credentials_not_built_in_defaults() -> None:
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


def test_readme_hero_image_uses_a_pypi_resolvable_url() -> None:
    source = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")

    assert (
        "https://raw.githubusercontent.com/cereja-project/govbr_auth/"
        "main/docs/media/fakegov-flow.svg"
    ) in source


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
