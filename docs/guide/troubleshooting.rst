🔧 Troubleshooting
===================

Erros Comuns
-----------

ValueError: cript_verifier_secret must be a valid 44-character Fernet key
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

**Causa**: `cript_verifier_secret` não é um valor Fernet válido.

**Solução**::

    from govbr_auth.utils import generate_cript_verifier_secret
    secret = generate_cript_verifier_secret()
    # Cole em seu .env

ValueError: Invalid or missing code_verifier
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

**Causa**: State foi corrompido, expirou ou secret foi trocado.

**Verificar**:

1. `cript_verifier_secret` é o mesmo entre requests
2. State não foi truncado na URL
3. Session não expirou (15 min aprox)

**Solução**: Gere novo authorize URL e tente novamente

GovBrAuthenticationError: JWT signature verification failed
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

**Causa**: Token JWT está inválido ou foi signed com secret diferente.

**Se em desenvolvimento**::

    # Certifique que jwt_secret bate
    GOVBR_JWT_SECRET=sua-chave-aqui

**Se em produção**:

    - Chaves públicas JWKS estão diferentes?
    - Issuer URL está correta?

**Solução**: Verifique logs e configuração de JWT

GovBrAuthenticationError: Token de ID não encontrado na resposta
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

**Causa**: Gov.br retornou erro ou resposta inválida.

**Verificar**:

1. `client_id` e `client_secret` estão corretos?
2. `redirect_uri` bate com registrado no Gov.br?
3. URLs de auth/token estão corretas?

**Solução**: Verifique `.env` e dados de cadastro no Gov.br

Endpoints Fake Não Aparecem
---------------------------

**Sintoma**: Acessar `http://localhost:8000/fake-govbr/authorize` retorna 404.

**Possíveis causas**:

1. **Modo fake não está ativado**

   ::

       config = GovBrConfig(..., use_fake=True)  # ← Necessário

2. **URLs não apontam para endpoints fake**

   ::

       config = GovBrConfig(
           govbr_auth_url="http://localhost:8000/fake-govbr/authorize",  # ✅
           govbr_token_url="http://localhost:8000/fake-govbr/token",      # ✅
           use_fake=True
       )

3. **Connector.init_*() não foi chamado**

   ::

       connector.init_fastapi(app)  # ← Registra as rotas

**Solução**: Verifique `.env` e código de inicialização

Login Fake Não Funciona
-----------------------

**Sintoma**: Página de login fake não aceita suas credenciais.

**Causas comuns**:

1. **CPF não está nos usuários padrão**

   Usuários padrão: 12345678901, 98765432100, 11122233344

   Crie custom fake users::

       from govbr_auth import FakeUserData

       fake_users = {
           "12345678901": FakeUserData(
               cpf="12345678901",
               nome="Seu Nome",
               email="seu@email.com"
           )
       }

       connector = GovBrConnector(config, fake_users=fake_users)

2. **Senha incorreta**

   A senha é sempre o CPF!

   ::

       CPF: 12345678901
       Senha: 12345678901  ✅

Callback de Sucesso Não é Chamado
----------------------------------

**Sintoma**: Após autenticação, callback não executa.

**Possíveis causas**:

1. **Callback não retorna Response válida (FastAPI)**

   ::

       # ❌ Errado
       def on_auth_success(data, request):
           return None  # FastAPI não sabe o que fazer

       # ✅ Correto
       def on_auth_success(data, request):
           return {"status": "ok"}

2. **Erro em callback está silencioso**

   Adicione try/except no callback::

       def on_auth_success(data, request):
           try:
               user = data["id_token_decoded"]
               # seu código
               return {"status": "ok"}
           except Exception as e:
               print(f"Erro: {e}")
               raise

3. **Callback é async mas não foi awaited (FastAPI)**

   O framework detecta automaticamente::

       # ✅ Ambos funcionam
       async def on_auth_success(data, request):
           await db.save_user(...)
           return {"status": "ok"}

CORS Bloqueando Requisição
--------------------------

**Sintoma**: Console do navegador mostra CORS error.

**Solução para FastAPI**::

    from fastapi.middleware.cors import CORSMiddleware

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "https://seu-app.com"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

**Solução para Flask**::

    from flask_cors import CORS

    app = Flask(__name__)
    CORS(app, origins=["http://localhost:3000", "https://seu-app.com"])

Estado Criptografado Perdido Após Redeploy
------------------------------------------

**Sintoma**: Ao reiniciar servidor, state fica inválido.

**Causa**: `cript_verifier_secret` mudou ou estado em cache foi perdido.

**Prevenção**:

1. **Mantenha mesmo secret entre deployments**

   ::

       # Todos os servers devem ter:
       CRIPT_VERIFIER_SECRET=mesmo-valor

2. **Estado válido por ~15 min**

   Não é esperado manter session entre restarts.

Redirect URI Mismatch
--------------------

**Sintoma**: Gov.br rejeita com "redirect_uri mismatch".

**Causa**: URL registrada no Gov.br não bate com usada no código.

**Verificar**:

1. Acesse cadastro no Gov.br
2. Copie exatamente o redirect_uri registrado
3. Cole em `.env`:

   ::

       GOVBR_REDIRECT_URI=https://seu-app.com/auth/govbr/callback

4. Verifique protocolo (http vs https)
5. Verifique porta
6. Verifique caminho exato

Endpoint Retorna 500
-------------------

**Sintoma**: POST/GET retorna 500 Internal Server Error.

**Verificar**:

1. Logs do servidor

   ::

       # FastAPI
       # O erro é exibido no console

2. `.env` está completo?

   ::

       # Campos obrigatórios
       GOVBR_CLIENT_ID=
       GOVBR_CLIENT_SECRET=
       GOVBR_REDIRECT_URI=
       CRIPT_VERIFIER_SECRET=
       GOVBR_AUTH_URL=
       GOVBR_TOKEN_URL=

3. Faça ping para Gov.br

   ::

       curl https://sso.acesso.gov.br/authorize

4. Firewall está bloqueando?

   Teste conectividade com Gov.br

Teste de Conectividade
----------------------

**Testar conexão com Gov.br**::

    python -c "
    import httpx
    try:
        r = httpx.get('https://sso.acesso.gov.br/authorize', timeout=10)
        print(f'Status: {r.status_code}')
    except Exception as e:
        print(f'Erro: {e}')
    "

**Testar fernet key**::

    from cryptography.fernet import Fernet
    from govbr_auth.utils import generate_cript_verifier_secret

    secret = generate_cript_verifier_secret()
    print(f"Válido: {len(secret) == 44}")

    # Ou teste uma chave existente
    secret = "Vvd9H5VC2Aqk-dwFOJX6MvQTuZZARmb37y7un9wkj0c="
    try:
        f = Fernet(secret.encode())
        print("Chave válida!")
    except:
        print("Chave inválida!")

Performance Lenta
-----------------

**Sintoma**: Login leva muito tempo.

**Possíveis causas**:

1. **Conexão lenta com Gov.br**

   - Teste latência: `ping sso.acesso.gov.br`
   - Tente diferentes regiões

2. **JWKS fetch lento**

   - Primeira chamada baixa chaves públicas (slow)
   - Depois cacham (rápido)

3. **Banco de dados no callback**

   - Se callback faz operações DB lentas
   - Otimize queries ou use async

Suporte e Ajuda
---------------

Se nenhuma solução acima funcionou:

1. Verifique `CHANGELOG.md` para known issues
2. Abra issue no `GitHub <https://github.com/cereja-project/govbr_auth/issues>`_
3. Inclua:

   - Versão Python
   - Versão biblioteca
   - Stack trace completo
   - `.env` (sem secrets)
   - Reprodução mínima

