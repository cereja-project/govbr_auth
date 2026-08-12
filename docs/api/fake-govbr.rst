Provedor fake explícito
=======================

O provedor local é opcional e nunca é ativado pelo cliente oficial. Instale o
extra ``govbr-auth[fake]`` e monte uma factory de ``govbr_auth.fake`` somente
no bootstrap de desenvolvimento.

.. autoclass:: govbr_auth.fake.FakeGovBrSettings

.. autoclass:: govbr_auth.fake.FakeGovBrProvider

.. autoclass:: govbr_auth.fake.FakeClient

.. autoclass:: govbr_auth.fake.FakeUser

.. autoclass:: govbr_auth.fake.InMemoryAuthorizationCodeReplayStore

.. autoclass:: govbr_auth.fake.InMemoryFakeUserStore

.. autofunction:: govbr_auth.fake.create_fake_govbr_router

.. autofunction:: govbr_auth.fake.create_fake_govbr_app
