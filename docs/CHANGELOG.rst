📝 Changelog
============

Migração para a API v1
----------------------

Esta versão separa a engine dos adapters de framework. O pacote base não exige
FastAPI, Django ou Flask; instale ``govbr-auth[fastapi]``,
``govbr-auth[django]`` ou ``govbr-auth[flask]`` conforme a aplicação. Use
``govbr_auth.core`` para o cliente estrito, os módulos de adapter para a
integração com a aplicação hospedeira e ``govbr_auth.fake`` somente quando o
provedor local for selecionado explicitamente.

O replay store em memória protege apenas uma instância do fake. Rejeição global
entre instâncias exigiria estado compartilhado, que não faz parte da
distribuição. Essa limitação é exclusiva do fake e não se aplica ao provedor
oficial Gov.br.

.. include:: ../CHANGELOG.md
   :parser: myst_parser.sphinx_

