Adaptador FastAPI
=================

Uso comum:

.. code-block:: python

   from govbr_auth.fastapi import AuthContext, GovBrAuth

   auth = GovBrAuth(on_success=authenticated)
   app.include_router(auth.router)

.. py:class:: GovBrAuth(*, on_success, on_error=None, expose_tokens=False, settings=None)

   Fachada que compõe o runtime selecionado e expõe ``router`` para montagem.

.. py:class:: AuthContext

   Contexto entregue ao handler após a validação completa da autenticação.

.. py:function:: create_govbr_router(runtime, *, on_success, on_error=None)

   Factory avançada para um runtime já composto.
