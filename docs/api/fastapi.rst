Adaptador FastAPI
=================

Uso comum:

.. code-block:: python

   from govbr_auth.fastapi import GovBrAuth

   auth = GovBrAuth(on_success=authenticated)
   app.include_router(auth.router)

``GovBrAuth`` aceita ``GovBrRuntimeSettings`` ou um ``GovBrRuntime`` já
composto. Quando ambos são omitidos, carrega ``GovBrRuntimeSettings`` do
ambiente. ``settings`` e ``runtime`` são mutuamente exclusivos. O adapter
registra apenas login e callback; a página demo pertence ao launcher FakeGov.

.. py:class:: GovBrAuth(*, on_success, settings=None, runtime=None, on_error=None, expose_tokens=False, prefix="/auth/govbr", clock=utc_now, user_repository=None)

   Fachada assíncrona que expõe ``router`` para inclusão explícita na
   aplicação.

.. py:class:: AuthContext

   Contexto entregue ao handler após a validação completa da autenticação.

.. py:function:: create_govbr_router(*, client, on_success, on_error=None, expose_tokens=False, prefix="/auth/govbr", clock=utc_now)

   Factory avançada para um ``GovBrClient`` já composto.
