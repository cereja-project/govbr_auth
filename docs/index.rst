GovBR Auth
==========

Biblioteca assíncrona para autenticação Gov.br em FastAPI com OAuth 2.0, PKCE e
OpenID Connect. O cliente valida ``state``, tokens RS256 por JWKS, ``issuer``,
``audience``, ``nonce`` e o vínculo do ``subject``.

O núcleo de composição é neutro de framework. O adaptador público disponível
nesta versão é FastAPI.

.. toctree::
   :maxdepth: 2
   :caption: Guia

   guide/quick-start
   guide/configuration
   guide/fake-mode
   guide/troubleshooting

.. toctree::
   :maxdepth: 2
   :caption: Referência da API

   api/core
   api/fastapi
   api/fake-govbr

.. toctree::
   :maxdepth: 1
   :caption: Versões

   CHANGELOG

Índice e busca
==============

* :ref:`genindex`
* :ref:`search`
