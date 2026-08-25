GovBR Auth
==========

Engine de autenticação Gov.br com adapters opcionais para FastAPI, Django e
Flask, usando OAuth 2.0, PKCE e OpenID Connect. O cliente valida ``state``, tokens RS256 por JWKS, ``issuer``,
``audience``, ``nonce`` e o vínculo do ``subject``.

O núcleo de composição é neutro de framework. Os adapters são instalados por
extras e se acoplam à aplicação hospedeira.

.. toctree::
   :maxdepth: 2
   :caption: Guia

   guide/quick-start
   guide/communication-flow
   guide/configuration
   guide/fake-mode
   guide/troubleshooting

.. toctree::
   :maxdepth: 2
   :caption: Referência da API

   api/core
   api/fastapi
   api/django
   api/flask
   api/fake-govbr

.. toctree::
   :maxdepth: 1
   :caption: Versões

   CHANGELOG

Índice e busca
==============

* :ref:`genindex`
* :ref:`search`
