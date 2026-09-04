Adaptador Flask
===============

Instalação::

   pip install "govbr-auth[flask]"

Uso:

.. code-block:: python

   from govbr_auth.flask import GovBrAuth

   auth = GovBrAuth(on_success=authenticated)
   auth.register(app)

``register(app)`` registra as rotas do consumidor e, em modo fake, as rotas
do FakeGov. Aceita ``GovBrRuntimeSettings`` ou ``GovBrRuntime``; quando
omitidos, carrega as configurações do ambiente. A página demo é responsabilidade
exclusiva do launcher FakeGov.

.. py:class:: GovBrAuth(*, on_success, settings=None, runtime=None, on_error=None, expose_tokens=False, prefix="/auth/govbr", clock=utc_now, user_repository=None)
   :no-index:

   Compõe o runtime e expõe ``blueprint`` ou ``register`` para registro manual.
