📝 Changelog
============

Migração para a API v1
----------------------

Esta versão remove os adaptadores Flask e Django, ``GovBrConnector``, o core
síncrono legado e a ativação fake implícita. O contrato público passa a ser
FastAPI-only e assíncrono. Use ``govbr_auth.core`` para o cliente estrito,
``govbr_auth`` para o adaptador FastAPI e ``govbr_auth.fake`` somente quando o
provedor local for instalado e montado explicitamente.

O replay store em memória protege apenas uma instância do fake. Rejeição global
entre instâncias exigiria estado compartilhado, que não faz parte da
distribuição. Essa limitação é exclusiva do fake e não se aplica ao provedor
oficial Gov.br.

.. include:: ../CHANGELOG.md
   :parser: myst_parser.sphinx_

