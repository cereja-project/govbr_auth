Adaptador FastAPI
=================

Uso comum:

.. code-block:: python

   from govbr_auth.fastapi import AuthContext, GovBrAuth

   auth = GovBrAuth(on_success=authenticated)
   app.include_router(auth.router)

.. py:class:: GovBrAuth(*, on_success, settings=None, runtime=None, on_error=None, expose_tokens=False, prefix="/auth/govbr", clock=utc_now, user_repository=None)

   Fachada que compõe o runtime selecionado e expõe ``router`` para montagem.
   ``settings`` e ``runtime`` são mutuamente exclusivos. ``user_repository``
   aceita um ``govbr_auth.fake.FakeUserRepository`` com o provedor fake. Em
   modo fake, o consumidor continua no mesmo runtime consumidor; a
   configuração troca apenas os endpoints do provedor e o transporte HTTP
   interno. Para composição avançada, o simulador canônico é
   ``govbr_auth.fake.FakeGovSimulator``, criado por
   ``govbr_auth.fake.create_fake_gov_simulator``.

.. py:class:: AuthContext

   Contexto entregue ao handler após a validação completa da autenticação.

.. py:function:: create_govbr_router(*, client, on_success, on_error=None, expose_tokens=False, prefix="/auth/govbr", clock=utc_now)

   Factory avançada que cria as rotas de autenticação sobre um
   ``GovBrClient`` já composto. ``client`` e ``on_success`` são obrigatórios
   e todos os argumentos são nomeados.
