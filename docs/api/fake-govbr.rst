FakeGov avançado
================

O provedor local é opcional e nunca é ativado pelo cliente oficial. Instale o
extra ``govbr-auth[fake]``. No caminho comum, selecione ``GOVBR_PROVIDER=fake``
e use ``GovBrAuth``; as factories abaixo atendem topologias avançadas.

.. autoclass:: govbr_auth.fake.FakeGovSimulator

.. autofunction:: govbr_auth.fake.create_fake_gov_simulator

.. autoclass:: govbr_auth.fake.FakeGovBrSettings

.. autoclass:: govbr_auth.fake.FakeGovBrProvider

.. autoclass:: govbr_auth.fake.FakeClient

.. autoclass:: govbr_auth.fake.FakeUser

.. autoclass:: govbr_auth.fake.InMemoryAuthorizationCodeReplayStore

.. autoclass:: govbr_auth.fake.InMemoryFakeUserStore

.. py:function:: create_fake_govbr_router(runtime, *, prefix=None, application=None, credential_authenticator=None, automatic_subject=None, clock=utc_now)

   Cria as rotas ASGI de um ``FakeGovSimulator`` ou ``FakeGovBrProvider``.
   ``application`` aceita uma ``FakeGovHttpApplication`` já composta. Com
   ``FakeGovSimulator``, omita esse argumento ou passe
   ``runtime.http_application`` para reutilizar a fachada canônica do simulador.

.. py:function:: create_fake_govbr_app(runtime, *, application=None, credential_authenticator=None, automatic_subject=None, clock=utc_now)

   Cria uma aplicação ASGI de provedor separado para uso avançado. Com
   ``FakeGovBrProvider`` cru, ``credential_authenticator`` e ``application``
   permitem composições manuais sem recriar o provider.
