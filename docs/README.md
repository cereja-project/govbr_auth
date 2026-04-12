# 📖 Documentação ReadTheDocs - Estrutura

Esta diretório contém toda a documentação do projeto, compilada com **Sphinx** e publicada no **ReadTheDocs**.

## Estrutura

```
docs/
├── conf.py                  # Configuração do Sphinx
├── index.rst               # Página principal (toctree)
├── requirements-docs.txt   # Dependências Sphinx
├── DEPLOYMENT.md           # Instruções de deploy
├── CHANGELOG.rst           # Link para CHANGELOG.md
├── guide/                  # Guias práticos
│   ├── quick-start.rst
│   ├── configuration.rst
│   ├── frameworks.rst
│   ├── security-practices.rst
│   ├── fake-mode.rst
│   ├── faq.rst
│   └── troubleshooting.rst
├── api/                    # Referência de API
│   ├── core.rst
│   ├── controller.rst
│   ├── fake-govbr.rst
│   └── utils.rst
├── boas_praticas_adotadas.md  # Markdown existente
├── modo_fake.md               # Markdown existente
└── _build/                 # Build output (ignorado no git)
    └── html/
```

## Build Local

```bash
# Instalar dependências
pip install -r docs/requirements-docs.txt

# Compilar HTML
cd docs
sphinx-build -b html . _build/html

# Abrir em navegador
# Windows
start _build/html/index.html
# macOS
open _build/html/index.html
# Linux
xdg-open _build/html/index.html
```

## Formatos de Output

Sphinx pode gerar múltiplos formatos:

```bash
# HTML (padrão)
sphinx-build -b html . _build/html

# PDF
sphinx-build -b pdf . _build/pdf

# EPUB
sphinx-build -b epub . _build/epub

# Man pages
sphinx-build -b man . _build/man
```

## Editar Documentação

### Adicionar Nova Página

1. Criar arquivo `.rst` em `guide/` ou `api/`
2. Adicionar à seção apropriada em `index.rst`:

```rst
.. toctree::
   :maxdepth: 2
   :caption: 📖 Minha Seção

   guide/minha-pagina
```

3. Build local com `sphinx-build`
4. Commit e push (ReadTheDocs faz rebuild automaticamente)

### Formatos Suportados

- **ReStructuredText** (`.rst`) - Recomendado para Sphinx
- **Markdown** (`.md`) - Via `myst-parser`
- **Docstrings Python** - Via `autodoc`

### Sintaxe Básica RST

```rst
Seção
=====

Subseção
--------

Parágrafo normal com `código inline` e **negrito**.

Lista:

- Item 1
- Item 2
  - Subitém

Código:

.. code-block:: python

   from govbr_auth import GovBrConfig
   config = GovBrConfig.from_env()

Ligação:

`Link texto <https://exemplo.com>`_

Referência cruzada:

:doc:`guide/quick-start`
:ref:`faq`

Aviso:

.. warning::

   Isso é um aviso importante!

Dica:

.. tip::

   Isso é uma dica útil.
```

## Configuração ReadTheDocs

Veja `.readthedocs.yml` na raiz do projeto.

Configuração principal:

- **Python 3.11**
- **Sphinx com RTD theme**
- **HTML + PDF + EPUB**
- **Build automático no push**

## Links

- [ReadTheDocs Project](https://readthedocs.org/projects/govbr-auth/)
- [Sphinx Documentation](https://www.sphinx-doc.org/)
- [MyST Parser](https://myst-parser.readthedocs.io/)
- [RTD Theme](https://sphinx-rtd-theme.readthedocs.io/)

## Troubleshooting

### Build falha com erro

1. Verifique logs no ReadTheDocs dashboard
2. Teste localmente: `sphinx-build -b html docs docs/_build/html`
3. Procure por warnings em `.readthedocs.yml`

### Mudanças não aparecem

1. ReadTheDocs pode levar minutos para rebuild
2. Força um rebuild manual no dashboard
3. Limpe cache: `rm -rf docs/_build/`

## Manutenção

- **Atualize links quebrados** conforme encontrados
- **Revise conteúdo desatualizado** regularmente
- **Adicione exemplos** quando há novas features
- **Mantenha consistência** com resto do projeto

---

Para mais detalhes sobre deploy, veja `DEPLOYMENT.md`.

