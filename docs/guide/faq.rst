❓ Perguntas Frequentes
========================

Qual é a diferença entre modo fake e produção?
-----------------------------------------------

.. list-table::
   :header-rows: 1

   * - Aspecto
     - Modo Fake
     - Produção
   * - Cadastro no Gov.br
     - ❌ Não necessário
     - ✅ Obrigatório
   * - Segurança
     - ⚠️ Baixa (dev only)
     - ✅ Alta (PKCE, JWKS)
   * - Verificação JWT
     - Hard-coded secret
     - Chaves públicas (RSA)
   * - Usuários
     - Pré-configurados
     - Reais do Gov.br
   * - HTTPS
     - ❌ HTTP ok
     - ✅ Obrigatório
   * - Sessão
     - Em memória
     - Destruída ao reiniciar

Como gerar o `cript_verifier_secret`?
-------------------------------------

Use a função auxiliar::

    from govbr_auth.utils import generate_cript_verifier_secret
    secret = generate_cript_verifier_secret()
    print(secret)  # Vvd9H5VC2Aqk-dwFOJX6MvQTuZZARmb37y7un9wkj0c=

Copie e cole em seu `.env` ou variáveis de ambiente.

⚠️ Não compartilhe este valor!

Como migrar de modo fake para produção?
---------------------------------------

1. **Cadastre sua aplicação no Gov.br**

   - Acesse `acesso.gov.br <https://acesso.gov.br/>`_
   - Siga o roteiro técnico
   - Receba `client_id` e `client_secret`

2. **Atualize a configuração**

   ::

       # .env
       USE_FAKE_GOVBR=false
       GOVBR_CLIENT_ID=seu-client-id-real
       GOVBR_CLIENT_SECRET=seu-client-secret-real
       GOVBR_AUTH_URL=https://sso.acesso.gov.br/authorize
       GOVBR_TOKEN_URL=https://sso.acesso.gov.br/token
       GOVBR_REDIRECT_URI=https://seu-app.com/auth/govbr/callback

3. **Remova a configuração fake**

   ::

       # Remova: govbr_auth_url/token_url apontando para localhost
       # Remova: fake_users do GovBrConnector

4. **Teste em staging primeiro**

   ::

       GOVBR_AUTH_URL=https://sso.staging.acesso.gov.br/authorize
       GOVBR_TOKEN_URL=https://sso.staging.acesso.gov.br/token

5. **Valide HTTPS e certificados**

   - HTTPS obrigatório
   - Certificados válidos
   - Redirect URI registrado

Qual é a diferença entre `code` e `code_verifier`?
--------------------------------------------------

- **`code`**: Autorização temporária retornada pelo Gov.br
  - Enviada ao backend por você
  - Válida por ~10 minutos

- **`code_verifier`**: Prova criptográfica PKCE
  - Gerada e criptografada pelo backend
  - Recuperada do `state` durante token exchange
  - Nunca exposta ao navegador

O `code` sozinho **não é suficiente** - o backend precisa provar que gerou o verifier correspondente.

Por que meu `state` é inválido?
------------------------------

Possíveis causas:

1. **`cript_verifier_secret` mudou**

   - State foi criptografado com SECRET_A
   - Backend agora usa SECRET_B
   - Descriptografia falha

   **Solução**: Use o mesmo secret em todos os deployments

2. **Sessão expirou**

   - State válido por ~15 minutos
   - Usuário esperou muito para fazer login

   **Solução**: Gere novo authorize URL

3. **URL corrompida**

   - State foi truncado ou modificado em trânsito
   - Proxy/firewall removeu caracteres

   **Solução**: Verifique logs, use HTTPS

Como debugar erros de autenticação?
----------------------------------

**Ative logging DEBUG**::

    import logging
    logging.basicConfig(level=logging.DEBUG)

**Erros comuns**:

- `"Invalid or missing code_verifier"` → State inválido/expirado
- `"JWT signature verification failed"` → Token fake ou secret errado
- `"Token de ID não encontrado na resposta"` → Gov.br retornou erro

Verifique o `.env` e logs do servidor.

Posso usar com mobile?
--------------------

Não diretamente, mas é possível:

**Opção 1: API Backend**

- App mobile → Backend GovBR Auth → Gov.br
- Backend retorna dados do usuário (JSON)
- Seguro, recomendado

**Opção 2: WebView**

- App mobile → WebView com sua página de login
- WebView redireciona a Gov.br
- Recupera callback com `code` + `state`
- Envia ao backend para trocar por token

**Opção 3: Redirect com Deep Link**

- App mobile → Gov.br (native)
- Gov.br redireciona via deep link
- App recupera `code` + `state`
- Envia ao backend

Recomendamos **Opção 1** por ser mais segura.

Preciso de dois deployments distintos (produção + staging)?
----------------------------------------------------------

Sim. Você precisa registrar os dois:

**Staging (Gov.br Staging)**::

    GOVBR_AUTH_URL=https://sso.staging.acesso.gov.br/authorize
    GOVBR_TOKEN_URL=https://sso.staging.acesso.gov.br/token
    GOVBR_CLIENT_ID=seu-staging-client-id

**Produção (Gov.br Produção)**::

    GOVBR_AUTH_URL=https://sso.acesso.gov.br/authorize
    GOVBR_TOKEN_URL=https://sso.acesso.gov.br/token
    GOVBR_CLIENT_ID=seu-production-client-id

Cada um com `redirect_uri` correspondente registrado no Gov.br.

Como resetar usuários fake?
--------------------------

O modo fake armazena sessões em memória. Ao reiniciar o servidor::

    uvicorn seu_app:app --reload

Todas as sessões são limpas e usuários voltam aos padrões.

Para customizar usuários fake::

    from govbr_auth import FakeUserData, GovBrConnector

    fake_users = {
        "12345678901": FakeUserData(
            cpf="12345678901",
            nome="Meu Usuário",
            email="user@example.com",
        )
    }

    connector = GovBrConnector(config, fake_users=fake_users)

Qual versão do Python é suportada?
---------------------------------

Python 3.11+ é obrigatório.

Testado em:

- Python 3.11
- Python 3.12
- Python 3.13
- Python 3.14

Como reportar bugs?
------------------

Abra uma issue no GitHub:

`github.com/cereja-project/govbr_auth/issues <https://github.com/cereja-project/govbr_auth/issues>`_

Por favor inclua:

- Versão do Python
- Versão da biblioteca (`pip show govbr-auth`)
- Framework usado (FastAPI/Flask/Django)
- Stack trace completo
- `.env` (sem secrets!)

