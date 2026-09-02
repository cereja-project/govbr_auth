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
BRAND_DIAGRAM_COLORS = {
    "#0f172a",
    "#111827",
    "#10b981",
    "#991b1b",
    "#ef4444",
    "#fef2f2",
    "#64748b",
    "#d1fae5",
    "#e2e8f0",
    "#f8fafc",
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


def _composite_color(foreground: str, background: str, opacity: float) -> str:
    foreground_channels = tuple(
        int(foreground[index : index + 2], 16) for index in (1, 3, 5)
    )
    background_channels = tuple(
        int(background[index : index + 2], 16) for index in (1, 3, 5)
    )
    channels = tuple(
        round(front * opacity + back * (1 - opacity))
        for front, back in zip(foreground_channels, background_channels)
    )
    return "#" + "".join(f"{channel:02x}" for channel in channels)


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
    temporarily_documented_variables = {"GOVBR_FAKE_END_TO_END"}

    assert supported_variables == expected_variables
    assert documented_variables == (
        expected_variables | temporarily_documented_variables
    )


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


def test_readme_leads_with_an_executable_configurable_application() -> None:
    source = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    required_guidance = (
        "from dotenv import load_dotenv",
        "GovBrRuntimeSettings.from_environment()",
        'if __name__ == "__main__":',
        "uvicorn.run(",
        "python myapp.py",
        "GovBrRuntimeSettings(",
        "GovBrProvider.FAKE",
        "context.user",
        "context.claims",
        "context.tokens",
    )

    assert all(guidance in source for guidance in required_guidance)


def test_readme_communication_section_embeds_animation_and_links_static_flow() -> None:
    source = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    animated_embed = (
        "![Fluxo animado de autenticação OAuth/OIDC entre navegador, aplicação "
        "e provedor]"
        "(https://raw.githubusercontent.com/cereja-project/govbr_auth/main/"
        "docs/media/authentication-sequence-animated.svg)"
    )
    static_link = (
        "[Ver versão estática do fluxo]"
        "(https://raw.githubusercontent.com/cereja-project/govbr_auth/main/"
        "docs/media/authentication-sequence.svg)"
    )
    section = re.search(
        r"^## Como a comunicação funciona\s*$.*?(?=^## |\Z)",
        source,
        flags=re.MULTILINE | re.DOTALL,
    )

    assert section is not None
    assert animated_embed in section.group()
    assert static_link in section.group()
    assert source.count(animated_embed) == 1
    assert source.count(static_link) == 1


def test_animated_authentication_flow_is_accessible_and_motion_safe() -> None:
    source = (DOCS_ROOT / "media" / "authentication-sequence-animated.svg").read_text(
        encoding="utf-8"
    )
    root = ET.fromstring(source)
    namespace = "{http://www.w3.org/2000/svg}"
    styles = root.findall(f".//{namespace}style")
    phases = {
        element.attrib["id"]
        for element in root.findall(f".//{namespace}g")
        if element.attrib.get("id", "").startswith("phase-")
    }

    assert root.attrib["role"] == "img"
    assert root.attrib["aria-labelledby"] == "title desc"
    assert root.find(f"{namespace}title") is not None
    assert root.find(f"{namespace}desc") is not None
    assert len(styles) == 1
    stylesheet = styles[0].text or ""
    phase_rule = re.search(r"\.phase\s*\{(?P<body>[^}]*)\}", stylesheet)
    reduced_motion_rule = re.search(
        r"@media\s*\(prefers-reduced-motion:\s*reduce\)\s*\{\s*"
        r"\.phase\s*\{(?P<body>[^}]*)\}",
        stylesheet,
    )

    assert phase_rule is not None
    opacity_match = re.search(r"opacity:\s*(?P<opacity>[\d.]+)", phase_rule["body"])
    assert opacity_match is not None
    inactive_text = _composite_color(
        "#0f172a", "#f8fafc", float(opacity_match["opacity"])
    )
    assert _contrast_ratio(inactive_text, "#f8fafc") >= 4.5
    assert reduced_motion_rule is not None
    assert "animation: none" in reduced_motion_rule["body"]
    assert "opacity: 1" in reduced_motion_rule["body"]
    assert phases == {f"phase-{number}" for number in range(1, 9)}
    assert root.findall(f".//{namespace}script") == []
    assert all(
        launcher_guidance not in source
        for launcher_guidance in (
            "python -m govbr_auth.fake",
            "END_TO_END",
            "Launcher",
            "launcher",
            "provider-only",
        )
    )


def test_sphinx_quickstart_keeps_the_optional_fake_launcher() -> None:
    source = (DOCS_ROOT / "guide" / "quick-start.rst").read_text(encoding="utf-8")

    assert 'pip install "govbr-auth[fake]"' in source
    assert "python -m govbr_auth.fake" in source
    assert "http://localhost:8000" in source


def test_fastapi_fake_quickstart_install_is_complete_for_uvicorn() -> None:
    required_guidance = (
        'pip install "govbr-auth[fastapi,fake]"',
        "python myapp.py",
        "http://localhost:8000/auth/govbr/login",
    )
    source = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")

    assert all(guidance in source for guidance in required_guidance)


def test_readme_leads_with_the_fakegov_value_and_visual_flow() -> None:
    source = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    sections = [line for line in source.splitlines() if line.startswith("## ")]
    assert sections[0] == "## Índice"
    assert sections[1] == "## Instalação"
    assert sections[2] == "## Teste a integração sem depender do gov.br"
    assert "docs/media/fakegov-flow.svg" in source
    assert "**FakeGov**" in source
    assert "Instalar" in source
    assert "Configurar" in source
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
    assert colors <= BRAND_DIAGRAM_COLORS
    assert "#10b981" in colors
    assert "#111827" in colors


@pytest.mark.parametrize(
    "filename",
    (
        "authentication-sequence.svg",
        "fakegov-flow.svg",
        "provider-switch.svg",
    ),
)
def test_versioned_diagrams_use_flat_surfaces(filename: str) -> None:
    root = ET.parse(DOCS_ROOT / "media" / filename).getroot()
    namespace = "{http://www.w3.org/2000/svg}"

    assert root.findall(f".//{namespace}linearGradient") == []
    assert root.findall(f".//{namespace}radialGradient") == []


@pytest.mark.parametrize(
    "filename",
    (
        "authentication-sequence.svg",
        "fakegov-flow.svg",
        "provider-switch.svg",
    ),
)
def test_versioned_diagrams_use_the_brand_typeface(filename: str) -> None:
    root = ET.parse(DOCS_ROOT / "media" / filename).getroot()
    families = {
        element.attrib["font-family"]
        for element in root.iter()
        if "font-family" in element.attrib
    }

    assert families == {"Inter, Arial, sans-serif"}


def test_fakegov_flow_step_numbers_have_readable_contrast() -> None:
    root = ET.parse(DOCS_ROOT / "media" / "fakegov-flow.svg").getroot()
    namespace = "{http://www.w3.org/2000/svg}"
    step_numbers = {"1", "2", "3", "4"}
    checked_steps = set()

    for group in root.findall(f".//{namespace}g"):
        circle = group.find(f"{namespace}circle")
        text = group.find(f"{namespace}text")
        if circle is None or text is None or text.text not in step_numbers:
            continue
        assert _contrast_ratio(text.attrib["fill"], circle.attrib["fill"]) >= 4.5
        checked_steps.add(text.text)

    assert checked_steps == step_numbers


def test_authentication_sequence_validation_uses_the_success_palette() -> None:
    root = ET.parse(DOCS_ROOT / "media" / "authentication-sequence.svg").getroot()
    namespace = "{http://www.w3.org/2000/svg}"
    validation = next(
        rect
        for rect in root.findall(f".//{namespace}rect")
        if rect.attrib.get("y") == "538"
    )

    assert validation.attrib["fill"] == "#d1fae5"
    assert validation.attrib["stroke"] == "#10b981"


@pytest.mark.parametrize(
    "filename",
    (
        "govbr-auth-logo.svg",
        "govbr-auth-logo-light.svg",
        "govbr-auth-logo-monochrome.svg",
        "govbr-auth-mark.svg",
        "govbr-auth-mark-light.svg",
        "govbr-auth-mark-monochrome.svg",
        "govbr-auth-mark-small.svg",
    ),
)
def test_brand_assets_are_accessible_self_contained_svgs(filename: str) -> None:
    source = (DOCS_ROOT / "media" / filename).read_text(encoding="utf-8")
    _assert_brand_svg_contract(source)


def test_brand_mark_family_is_complete() -> None:
    expected = {
        "govbr-auth-mark.svg",
        "govbr-auth-mark-light.svg",
        "govbr-auth-mark-monochrome.svg",
        "govbr-auth-mark-small.svg",
    }

    assert expected <= {path.name for path in (DOCS_ROOT / "media").iterdir()}


@pytest.mark.parametrize(
    "filename",
    (
        "govbr-auth-mark.svg",
        "govbr-auth-mark-light.svg",
        "govbr-auth-mark-monochrome.svg",
        "govbr-auth-mark-small.svg",
    ),
)
def test_brand_marks_use_the_network_connector(filename: str) -> None:
    root = ET.parse(DOCS_ROOT / "media" / filename).getroot()
    namespace = "{http://www.w3.org/2000/svg}"

    assert len(root.findall(f".//{namespace}path")) == 2


def test_brand_mark_variants_share_the_same_connector_geometry() -> None:
    namespace = "{http://www.w3.org/2000/svg}"
    filenames = (
        "govbr-auth-mark.svg",
        "govbr-auth-mark-light.svg",
        "govbr-auth-mark-monochrome.svg",
    )
    connectors = {
        tuple(
            path.attrib["d"]
            for path in ET.parse(DOCS_ROOT / "media" / filename)
            .getroot()
            .findall(f".//{namespace}path")
        )
        for filename in filenames
    }

    assert connectors == {
        (
            "M 32 10 V 22 L 22 32 V 38",
            "M 32 22 L 42 32 V 38",
        )
    }


def test_small_brand_mark_compensates_for_sixteen_pixels() -> None:
    root = ET.parse(DOCS_ROOT / "media" / "govbr-auth-mark-small.svg").getroot()
    namespace = "{http://www.w3.org/2000/svg}"
    connector = root.find(f".//{namespace}path")
    cherries = root.findall(f".//{namespace}circle")

    assert connector is not None
    assert connector.attrib["d"] == "M 32 10 V 22 L 22 32 V 38"
    assert len(cherries) == 6
    assert {circle.attrib["r"] for circle in cherries} == {"3", "4", "11"}
    assert any(
        group.attrib.get("stroke-width") == "5"
        for group in root.findall(f".//{namespace}g")
    )


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

    fruit = [cherry for cherry in cherries if cherry.attrib.get("r") == "11"]
    assert len(fruit) == 2
    assert all(
        float(cherry.attrib["cy"]) + float(cherry.attrib["r"]) <= 64 for cherry in fruit
    )


@pytest.mark.parametrize(
    "filename",
    (
        "govbr-auth-logo.svg",
        "govbr-auth-logo-light.svg",
        "govbr-auth-logo-monochrome.svg",
    ),
)
def test_wordmark_viewbox_is_optically_centered(filename: str) -> None:
    root = ET.parse(DOCS_ROOT / "media" / filename).getroot()

    assert root.attrib["viewBox"] == "0 0 360 96"


@pytest.mark.parametrize(
    "filename",
    (
        "govbr-auth-logo.svg",
        "govbr-auth-logo-light.svg",
        "govbr-auth-logo-monochrome.svg",
    ),
)
def test_wordmark_hyphen_does_not_overlap_the_r(filename: str) -> None:
    root = ET.parse(DOCS_ROOT / "media" / filename).getroot()
    namespace = "{http://www.w3.org/2000/svg}"
    wordmark = root.findall(f"{namespace}path")

    assert len(wordmark) == 2

    translations = []
    for path in wordmark:
        match = re.fullmatch(
            r"translate\((-?\d+(?:\.\d+)?) 0\)", path.attrib.get("transform", "")
        )
        assert match is not None
        translations.append(float(match.group(1)))

    r_right_edge = 244.937 + translations[0]
    hyphen_left_edge = 232.893 + translations[1]

    assert hyphen_left_edge - r_right_edge >= 3


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


def test_light_wordmark_contrasts_with_the_sphinx_header() -> None:
    root = ET.parse(DOCS_ROOT / "media" / "govbr-auth-logo-light.svg").getroot()
    namespace = "{http://www.w3.org/2000/svg}"
    wordmark_colors = {
        path.attrib["fill"]
        for path in root.findall(f"{namespace}path")
        if "fill" in path.attrib
    }
    sphinx_config = runpy.run_path(str(DOCS_ROOT / "conf.py"))
    header_background = sphinx_config["html_theme_options"][
        "style_nav_header_background"
    ]

    assert header_background == "#111827"
    assert wordmark_colors == {"#ffffff", "#94a3b8"}
    assert all(
        _contrast_ratio(color, header_background) >= 3 for color in wordmark_colors
    )


def test_documentation_entrypoints_publish_the_brand_assets() -> None:
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    sphinx_config = runpy.run_path(str(DOCS_ROOT / "conf.py"))

    assert (
        '<source media="(prefers-color-scheme: dark)" '
        'srcset="https://raw.githubusercontent.com/cereja-project/govbr_auth/'
        'main/docs/media/govbr-auth-logo-light.svg">'
    ) in readme
    assert (
        '<source media="(prefers-color-scheme: light)" '
        'srcset="https://raw.githubusercontent.com/cereja-project/govbr_auth/'
        'main/docs/media/govbr-auth-logo.svg">'
    ) in readme
    assert (
        "https://raw.githubusercontent.com/cereja-project/govbr_auth/"
        "main/docs/media/govbr-auth-logo.svg"
    ) in readme
    assert sphinx_config["html_theme_options"]["logo_only"] is True
    assert sphinx_config["html_logo"] == "media/govbr-auth-logo-light.svg"
    assert sphinx_config["html_favicon"] == "media/govbr-auth-mark-small.svg"
    assert "_static" in sphinx_config["html_static_path"]
    assert "brand.css" in sphinx_config["html_css_files"]


def test_sphinx_theme_uses_the_approved_brand_and_local_fonts() -> None:
    stylesheet = (DOCS_ROOT / "_static" / "brand.css").read_text(encoding="utf-8")

    assert "--brand-graphite: #111827;" in stylesheet
    assert "--brand-green: #10b981;" in stylesheet
    assert "--brand-red: #ef4444;" in stylesheet
    assert "--brand-wine: #991b1b;" in stylesheet
    assert 'font-family: "Inter"' in stylesheet
    assert 'font-family: "JetBrains Mono"' in stylesheet
    assert 'url("fonts/InterVariable.woff2")' in stylesheet
    assert "#1351b4" not in stylesheet
    assert "gradient(" not in stylesheet
    assert ".rst-content a:hover" in stylesheet
    assert ".rst-content code" in stylesheet
    assert stylesheet.count("color: var(--link);") >= 3


def test_brand_guide_publishes_the_approved_usage_contract() -> None:
    index = (DOCS_ROOT / "index.rst").read_text(encoding="utf-8")
    guide = (DOCS_ROOT / "guide" / "brand.rst").read_text(encoding="utf-8")
    normalized_guide = _normalized_prose(guide)
    descriptor = "biblioteca python open source para integração com gov.br"

    assert "guide/brand" in _toctree_entries(index)
    assert descriptor in normalized_guide
    assert "50% da altura visível" in normalized_guide
    assert "mínimo de 24 px" in normalized_guide
    assert "16 a 23 px" in normalized_guide
    assert "#111827" in normalized_guide
    assert "#10b981" in normalized_guide
    assert "#ef4444" in normalized_guide
    assert "#991b1b" in normalized_guide
    assert "inter" in normalized_guide
    assert "jetbrains mono" in normalized_guide
    assert "autenticamente pythônico" in normalized_guide
    assert "variante monocromática branca" not in normalized_guide
    assert "não use a marca para sugerir homologação ou endosso" in normalized_guide


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


def test_installable_fake_commands_are_exact_lines_in_every_instruction() -> None:
    instructions = (
        (
            (PROJECT_ROOT / "README.md").read_text(encoding="utf-8"),
            'pip install "govbr-auth[fastapi,fake]"',
        ),
        (
            (DOCS_ROOT / "guide" / "quick-start.rst").read_text(encoding="utf-8"),
            'pip install "govbr-auth[fake]"',
        ),
        (
            (DOCS_ROOT / "guide" / "troubleshooting.rst").read_text(encoding="utf-8"),
            'pip install "govbr-auth[fake]"',
        ),
    )

    assert all(
        any(command == line.strip() for line in source.splitlines())
        for source, command in instructions
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
    common_guidance = (
        "GOVBR_FAKE_USERS_FILE",
        "fake-users.local.json",
        '"users"',
        '"cpf": "11122233344"',
        '"password": "senha-ficticia"',
        "não use credenciais reais",
    )

    source = document.read_text(encoding="utf-8")

    assert all(guidance in source for guidance in common_guidance)
    if document == PROJECT_ROOT / "README.md":
        assert "python myapp.py" in source
        assert "GOVBR_PROVIDER=fake" in source
    else:
        assert 'export GOVBR_FAKE_USERS_FILE="$PWD/fake-users.local.json"' in source
        assert '$env:GOVBR_FAKE_USERS_FILE = "$PWD\\fake-users.local.json"' in source
        assert "python -m govbr_auth.fake" in source


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
