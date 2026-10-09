"""Validate a release tag using source metadata without importing the package."""

import argparse
import ast
from pathlib import Path
import tomllib


def release_version(root: Path) -> str:
    with (root / "pyproject.toml").open("rb") as stream:
        metadata = tomllib.load(stream)
    project = metadata["project"]
    if "version" in project:
        version = project["version"]
    else:
        if "version" not in project.get("dynamic", []):
            raise ValueError("versão não declarada nos metadados")
        source = metadata["tool"]["setuptools"]["dynamic"]["version"]["attr"]
        if source != "govbr_auth.__version__":
            raise ValueError("fonte da versão dinâmica não suportada")
        module = ast.parse(
            (root / "govbr_auth" / "__init__.py").read_text(encoding="utf-8")
        )
        values = [
            node.value
            for node in module.body
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "__version__"
                for target in node.targets
            )
        ]
        if len(values) != 1:
            raise ValueError("versão literal única não encontrada no pacote")
        version = ast.literal_eval(values[0])
    if not isinstance(version, str) or not version or version != version.strip():
        raise ValueError("versão deve ser uma string não vazia, sem espaços externos")
    return version


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tag")
    arguments = parser.parse_args()
    try:
        expected = f"v{release_version(Path.cwd())}"
    except (OSError, KeyError, ValueError, TypeError, SyntaxError) as error:
        parser.exit(1, f"Não foi possível validar a versão: {error}\n")
    if arguments.tag != expected:
        parser.exit(
            1, f"Tag divergente: esperado {expected}, recebido {arguments.tag}\n"
        )
    print(f"Tag confirmada: {expected}")


if __name__ == "__main__":
    main()
