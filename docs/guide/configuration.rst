Configuração
============

Seleção do provedor
-------------------

``GOVBR_PROVIDER`` aceita somente ``official`` ou ``fake``. O default é
``official``. Use ``GOVBR_PROVIDER=fake`` apenas em desenvolvimento.

Provedor oficial
----------------

.. code-block:: text

    GOVBR_PROVIDER=official
    GOVBR_ENVIRONMENT=production
    GOVBR_AUTHORIZATION_URL=https://sso.acesso.gov.br/authorize
    GOVBR_TOKEN_URL=https://sso.acesso.gov.br/token
    GOVBR_USERINFO_URL=https://sso.acesso.gov.br/userinfo/
    GOVBR_CLIENT_ID=seu-client-id
    GOVBR_CLIENT_SECRET=seu-client-secret
    GOVBR_REDIRECT_URI=https://app.example/auth/govbr/callback
    GOVBR_TRANSACTION_SECRET=substitua-pelo-valor-gerado
    GOVBR_ISSUER=https://sso.acesso.gov.br/
    GOVBR_JWKS_URL=https://sso.acesso.gov.br/jwk

``GOVBR_TRANSACTION_SECRET`` protege ``state``, nonce e PKCE. Gere uma vez:

.. code-block:: python

    from govbr_auth import generate_transaction_secret

    print(generate_transaction_secret())

Mantenha o valor secreto e use o mesmo valor em todas as instâncias. Não gere
uma chave nova a cada inicialização.

O backend suporta múltiplos workers sem armazenamento compartilhado porque o
``state`` contém um envelope de transação cifrado e autenticado por Fernet.
Todos os workers precisam da mesma secret ``GOVBR_TRANSACTION_SECRET``. O
envelope tem TTL e preserva os vínculos de PKCE e nonce até o callback.

O ``state`` não é um registro de uso único e pode ser decodificado novamente
durante o TTL. A prevenção de replay é responsabilidade do authorization code
de uso único: o provedor deve invalidá-lo de forma atômica após a primeira
troca. Rotacionar a secret invalida os fluxos que ainda estiverem em andamento.

FakeGov
-------

``GOVBR_FAKE_END_TO_END`` aceita apenas ``true`` ou ``false``. Host, porta,
prefixo e fonte de usuários podem ser alterados por ``GOVBR_FAKE_HOST``,
``GOVBR_FAKE_PORT``, ``GOVBR_FAKE_PROVIDER_PREFIX`` e
``GOVBR_FAKE_USERS_FILE``. O host precisa ser ``localhost``, ``127.0.0.1`` ou
``::1``.

Configuração explícita
----------------------

Aplicações avançadas podem construir ``GovBrRuntimeSettings`` e passá-lo a
``GovBrAuth``. O caminho comum deve preferir variáveis de ambiente e a fachada
do adapter escolhido, mantendo a composição em um único lugar.
