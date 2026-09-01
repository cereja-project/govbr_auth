Publicação
==========

Este guia descreve a publicação do pacote; ele não substitui a revisão do
conteúdo da release no GitHub.

Pré-requisito único no PyPI
---------------------------

Configure um `Trusted Publisher do GitHub Actions
<https://docs.pypi.org/trusted-publishers/adding-a-publisher/>`_ para o projeto
``govbr-auth`` com estes valores:

* owner: ``cereja-project``;
* repository: ``govbr_auth``;
* workflow: ``pythonpublish.yml``;
* environment: ``pypi``.

O workflow não usa usuário, senha ou token persistente. O job ``publish``
solicita um token OIDC de curta duração e só executa depois que o job
``verify-and-build`` produz e valida o wheel e o sdist.

Checklist da versão
-------------------

#. Confirme que a versão coincide em ``pyproject.toml``,
   ``govbr_auth/__init__.py``, ``docs/conf.py`` e ``CHANGELOG.md``.
#. Execute os gates locais::

       # Substitua {TEMP} por um diretório temporário absoluto fora do checkout
       # e aponte COVERAGE_FILE para {TEMP}/.coverage antes de executar o pytest.

       python -m black --check govbr_auth tests examples scripts
       python -m flake8 govbr_auth tests examples scripts --count --select=E9,F63,F7,F82 --show-source --statistics
       python -m pytest --cov=govbr_auth --cov-branch --cov-fail-under=90 --basetemp "{TEMP}/pytest" -o cache_dir="{TEMP}/pytest-cache"
       python -m build --outdir "{TEMP}/dist"
       python -m twine check "{TEMP}/dist/"*
       python -m sphinx -W -b html docs "{TEMP}/docs-html"
       python -m sphinx -W -b linkcheck docs "{TEMP}/docs-linkcheck"

#. Faça merge da candidata em ``origin/main`` somente após a matriz da CI
   aprovar Linux, Windows e macOS em Python 3.11 a 3.14.
#. Crie uma GitHub Release publicada a partir da tag da versão. Uma release em
   rascunho não publica o pacote.
#. O workflow rejeita tags diferentes de ``v<versão>``, commits que não
   pertencem a ``origin/main`` e wheels que falhem na instalação isolada ou nos
   smokes de FastAPI, Django, Flask e FakeGov.
#. Confirme o sucesso do environment ``pypi`` e valide a instalação em um venv
   vazio.

As atestações de publicação são produzidas automaticamente pelo action oficial
do PyPA. Consulte a `documentação de atestações do PyPI
<https://docs.pypi.org/attestations/producing-attestations/>`_.
