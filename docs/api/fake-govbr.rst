FakeGov avançado
================

O FakeGov é um provedor local opcional, habilitado explicitamente com
``GOVBR_PROVIDER=fake``. O caminho comum usa ``GovBrAuth``. O comando
``python -m govbr_auth.fake`` inicia o launcher end-to-end em loopback e
publica a página demo na raiz ``/``; ``/govbr-auth-demo`` permanece como alias.
Essa apresentação não pertence aos adapters nem ao provedor oficial.

.. autoclass:: govbr_auth.fake.FakeGovSimulator

.. autofunction:: govbr_auth.fake.create_fake_gov_simulator

``FakeGovHttpApplication`` é a fachada HTTP neutra do simulador. Com um
``FakeGovSimulator``, reutilize ``runtime.http_application`` quando precisar
fornecer uma aplicação HTTP já composta.

.. autoclass:: govbr_auth.fake.FakeGovBrSettings

.. autoclass:: govbr_auth.fake.FakeGovBrProvider

.. autoclass:: govbr_auth.fake.FakeClient

.. autoclass:: govbr_auth.fake.FakeUser

.. autoclass:: govbr_auth.fake.InMemoryAuthorizationCodeReplayStore

.. autoclass:: govbr_auth.fake.InMemoryFakeUserStore

.. py:function:: create_fake_app(settings=None, *, clock=utc_now, user_repository=None)

   Cria a aplicação local completa com consumidor, FakeGov e página demo.

.. py:function:: create_fake_govbr_router(runtime, *, prefix=None, application=None, credential_authenticator=None, automatic_subject=None, clock=utc_now)

   Cria apenas as rotas do provedor FakeGov para topologias avançadas.

.. py:function:: create_fake_govbr_app(runtime, *, application=None, credential_authenticator=None, automatic_subject=None, clock=utc_now)

   Cria uma aplicação ASGI somente do provedor FakeGov.
