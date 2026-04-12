⚙️ Configuração
================

Visão Geral
-----------

A biblioteca oferece configuração flexível via:

1. **Arquivo `.env`** (recomendado para desenvolvimento)
2. **Variáveis de ambiente** (recomendado para produção)
3. **Código Python** (para casos específicos)

Variáveis de Ambiente
---------------------

.. code-block:: bash

    # Identidade da aplicação
    GOVBR_CLIENT_ID=your-client-id
    GOVBR_CLIENT_SECRET=your-client-secret
    GOVBR_REDIRECT_URI=https://seu-app.com/auth/govbr/callback

    # Endpoints Gov.br (produção/staging/fake)
    GOVBR_AUTH_URL=https://sso.acesso.gov.br/authorize
    GOVBR_TOKEN_URL=https://sso.acesso.gov.br/token

    # Segurança
    CRIPT_VERIFIER_SECRET=Vvd9H5VC2Aqk-dwFOJX6MvQTuZZARmb37y7un9wkj0c=
    JWT_SECRET=your-jwt-secret

    # OAuth 2.0 (opcionais, têm padrões)
    GOVBR_SCOPE=openid profile email
    GOVBR_RESPONSE_TYPE=code
    GOVBR_CODE_CHALLENGE_METHOD=S256

    # Modo desenvolvimento
    USE_FAKE_GOVBR=false

Carregando de `.env`
--------------------

.. code-block:: python

    from govbr_auth import GovBrConfig

    # Carrega automaticamente do .env
    config = GovBrConfig.from_env()

Configuração Explícita
----------------------

.. code-block:: python

    from govbr_auth import GovBrConfig

    config = GovBrConfig(
        client_id="seu-client-id",
        client_secret="seu-client-secret",
        redirect_uri="https://seu-app.com/auth/govbr/callback",
        cript_verifier_secret="Vvd9H5VC2Aqk-dwFOJX6MvQTuZZARmb37y7un9wkj0c=",
        govbr_auth_url="https://sso.acesso.gov.br/authorize",
        govbr_token_url="https://sso.acesso.gov.br/token",
        jwt_secret="seu-jwt-secret",
        use_fake=False,  # False para produção
    )

Gerando `cript_verifier_secret`
--------------------------------

O `cript_verifier_secret` é uma chave criptográfica Fernet (32 bytes, base64). Você **deve** gerar um valor único e seguro:

.. code-block:: python

    from govbr_auth.utils import generate_cript_verifier_secret

    secret = generate_cript_verifier_secret()
    print(secret)
    # Exemplo: Vvd9H5VC2Aqk-dwFOJX6MvQTuZZARmb37y7un9wkj0c=

⚠️ **Importante**: Este valor deve ser:

- Mantido em segredo (nunca commitar no git)
- **Idêntico** em todos os ambientes de um deployment
- Incluído no `.env` ou variáveis de ambiente seguras

Se você trocar este valor, **todos os estados criptografados anteriores se tornarão inválidos**.

Modo Fake (Desenvolvimento)
----------------------------

Para desenvolvimento sem cadastro no Gov.br, ative o modo fake:

.. code-block:: python

    config = GovBrConfig(
        client_id="fake-client-id",
        client_secret="fake-client-secret",
        redirect_uri="http://localhost:8000/auth/govbr/callback",
        cript_verifier_secret="Vvd9H5VC2Aqk-dwFOJX6MvQTuZZARmb37y7un9wkj0c=",
        govbr_auth_url="http://localhost:8000/fake-govbr/authorize",
        govbr_token_url="http://localhost:8000/fake-govbr/token",
        use_fake=True,  # Ativa modo fake
    )

Ou via `.env`::

    USE_FAKE_GOVBR=true
    GOVBR_AUTH_URL=http://localhost:8000/fake-govbr/authorize
    GOVBR_TOKEN_URL=http://localhost:8000/fake-govbr/token

Validação de Configuração
--------------------------

A configuração é validada automaticamente no construtor `GovBrConfig()`. Se algo estiver faltando ou inválido, você verá:

.. code-block:: python

    ValueError: cript_verifier_secret must be a valid 44-character Fernet key

Verifique:

- `cript_verifier_secret` tem exatamente 44 caracteres (base64)
- `client_id` e `client_secret` não estão vazios
- `redirect_uri` é uma URL válida
- `govbr_auth_url` e `govbr_token_url` são URLs válidas

Ambientes Suportados
---------------------

**Desenvolvimento Local**::

    USE_FAKE_GOVBR=true
    GOVBR_AUTH_URL=http://localhost:8000/fake-govbr/authorize
    GOVBR_TOKEN_URL=http://localhost:8000/fake-govbr/token

**Staging (Gov.br Staging)**::

    USE_FAKE_GOVBR=false
    GOVBR_AUTH_URL=https://sso.staging.acesso.gov.br/authorize
    GOVBR_TOKEN_URL=https://sso.staging.acesso.gov.br/token

**Produção (Gov.br Produção)**::

    USE_FAKE_GOVBR=false
    GOVBR_AUTH_URL=https://sso.acesso.gov.br/authorize
    GOVBR_TOKEN_URL=https://sso.acesso.gov.br/token

Referência de Campos
--------------------

.. list-table::
   :header-rows: 1

   * - Campo
     - Tipo
     - Obrigatório
     - Descrição
   * - `client_id`
     - str
     - ✅
     - ID de cliente fornecido pelo Gov.br
   * - `client_secret`
     - str
     - ✅
     - Secret de cliente (manter em segredo!)
   * - `redirect_uri`
     - str
     - ✅
     - URL para redirecionamento pós-autenticação
   * - `cript_verifier_secret`
     - str
     - ✅
     - Chave Fernet (44 chars base64) para criptografia de state
   * - `govbr_auth_url`
     - str
     - ✅
     - URL de autorização do Gov.br
   * - `govbr_token_url`
     - str
     - ✅
     - URL de token do Gov.br
   * - `jwt_secret`
     - str
     - ❌
     - Secret para verificação JWT (opcional em produção com JWKS)
   * - `use_fake`
     - bool
     - ❌
     - Ativa modo fake (padrão: False)
   * - `scope`
     - str
     - ❌
     - Escopos OAuth (padrão: "openid profile email")
   * - `response_type`
     - str
     - ❌
     - Tipo de resposta (padrão: "code")
   * - `code_challenge_method`
     - str
     - ❌
     - Método PKCE (padrão: "S256")

