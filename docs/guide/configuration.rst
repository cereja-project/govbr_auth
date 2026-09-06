Configuração
============

Seleção do provedor
-------------------

``GOVBR_PROVIDER`` aceita somente ``official`` ou ``fake``. O default é
``official``. Use ``fake`` apenas em desenvolvimento e testes.

``GovBrRuntimeSettings.from_environment()`` é a única leitura comum de
configuração. Nomes desconhecidos com prefixo ``GOVBR_`` são rejeitados;
variáveis reconhecidas, mas inativas para o provedor selecionado, geram apenas
warning sem incluir valores ou segredos.

Provedor oficial
----------------

As configurações do cliente são compartilhadas entre o provedor oficial e o
FakeGov. Os endpoints abaixo são exclusivos do provedor oficial.

.. code-block:: text

    GOVBR_PROVIDER=official
    GOVBR_ENVIRONMENT=production
    GOVBR_AUTHORIZATION_URL=https://sso.acesso.gov.br/authorize
    GOVBR_TOKEN_URL=https://sso.acesso.gov.br/token
    GOVBR_USERINFO_URL=https://sso.acesso.gov.br/userinfo/
    GOVBR_ISSUER=https://sso.acesso.gov.br/
    GOVBR_JWKS_URL=https://sso.acesso.gov.br/jwk

Configure sempre as variáveis comuns do cliente uma única vez::

    GOVBR_CLIENT_ID=seu-client-id
    GOVBR_CLIENT_SECRET=seu-client-secret
    GOVBR_REDIRECT_URI=https://app.example/auth/govbr/callback
    GOVBR_LOGOUT_URL=https://sso.acesso.gov.br/logout
    GOVBR_POST_LOGOUT_REDIRECT_URI=https://app.example/auth/signed-out
    GOVBR_TRANSACTION_SECRET=substitua-pelo-valor-gerado

Os endpoints oficiais devem pertencer ao mesmo ambiente. Fora de loopback,
``GOVBR_REDIRECT_URI`` exige HTTPS e deve coincidir exatamente com a URI
cadastrada no Gov.br.

O logout é habilitado quando ``GOVBR_LOGOUT_URL`` e
``GOVBR_POST_LOGOUT_REDIRECT_URI`` são configurados juntos. A URI de retorno
deve estar previamente autorizada no provedor; a biblioteca não aceita esse
destino pela query string da rota local.

``GOVBR_TRANSACTION_SECRET`` protege ``state``, nonce e PKCE. Gere uma vez:

.. code-block:: python

    from govbr_auth import generate_transaction_secret

    print(generate_transaction_secret())

Mantenha o valor secreto e use o mesmo valor em todas as instâncias e workers.
O ``state`` não é um registro de uso
único; a prevenção de replay depende do authorization code descartável do
provedor.

O envelope usa Fernet e TTL, além de PKCE e nonce. O ``state`` não é um
registro de uso único; a prevenção de replay depende do authorization code de
uso único do provedor.

O backend é stateless, funciona com múltiplos workers sem armazenamento
compartilhado e mantém a mesma secret em todas as instâncias.

FakeGov
-------

Defina ``GOVBR_PROVIDER=fake`` e ``GOVBR_ENVIRONMENT=local``. O FakeGov
reutiliza ``GOVBR_CLIENT_ID``, ``GOVBR_CLIENT_SECRET``,
``GOVBR_REDIRECT_URI``, ``GOVBR_SCOPE`` e ``GOVBR_TRANSACTION_SECRET``; não
existe uma segunda configuração de cliente para o simulador.

``GOVBR_FAKE_HOST``, ``GOVBR_FAKE_PORT``, ``GOVBR_FAKE_PROVIDER_PREFIX`` e
``GOVBR_FAKE_USERS_FILE`` controlam o simulador local. O host é restrito a
``localhost``, ``127.0.0.1`` e ``::1``. O launcher ``python -m govbr_auth.fake``
monta o fluxo end-to-end e a página demo na raiz em loopback.

Configuração explícita
----------------------

Aplicações podem construir diretamente ``GovBrRuntimeSettings`` e passá-lo ao
adapter:

.. code-block:: python

    from govbr_auth.runtime import GovBrProvider, GovBrRuntimeSettings

    settings = GovBrRuntimeSettings(provider=GovBrProvider.FAKE)
    auth = GovBrAuth(settings=settings, on_success=authenticated)
