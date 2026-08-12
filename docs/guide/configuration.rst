Configuração
============

O exemplo lê somente a seleção do ambiente, endpoints, credenciais OAuth,
redirect e o segredo local de transações do consumidor:

.. code-block:: text

    GOVBR_ENVIRONMENT=production
    GOVBR_AUTHORIZATION_URL=https://sso.acesso.gov.br/authorize
    GOVBR_TOKEN_URL=https://sso.acesso.gov.br/token
    GOVBR_USERINFO_URL=https://sso.acesso.gov.br/userinfo/
    GOVBR_CLIENT_ID=seu-client-id
    GOVBR_CLIENT_SECRET=seu-client-secret
    GOVBR_REDIRECT_URI=https://app.example/auth/govbr/callback
    GOVBR_TRANSACTION_SECRET=uma-chave-fernet-do-consumidor
    GOVBR_ISSUER=https://sso.acesso.gov.br/
    GOVBR_JWKS_URL=https://sso.acesso.gov.br/jwk

``GOVBR_TRANSACTION_SECRET`` protege ``state``, nonce e PKCE armazenados pelo
consumidor. Não é uma credencial fornecida pelo provedor e deve permanecer
secreto e estável entre processos do mesmo deployment.

Configuração explícita
----------------------

.. code-block:: python

    from pydantic import SecretStr
    from govbr_auth.core import GovBrSettings

    settings = GovBrSettings(
        authorization_url="https://sso.acesso.gov.br/authorize",
        token_url="https://sso.acesso.gov.br/token",
        userinfo_url="https://sso.acesso.gov.br/userinfo/",
        client_id="seu-client-id",
        client_secret=SecretStr("seu-client-secret"),
        redirect_uri="https://app.example/auth/govbr/callback",
        transaction_secret=SecretStr("uma-chave-fernet-do-consumidor"),
        issuer="https://sso.acesso.gov.br/",
        jwks_url="https://sso.acesso.gov.br/jwk",
    )

HTTP sem TLS é aceito apenas quando ``environment="local"`` e todas as URLs
usam host de loopback. Não existe ``use_fake``: o fake é montado explicitamente
no bootstrap de desenvolvimento.
