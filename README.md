# GovBR Auth

Autentique usuários com o Gov.br usando FastAPI, Flask, Django ou sua própria stack personalizada.

## 🚀 Instalação

Instalação mínima (somente núcleo de serviços):
```bash
pip install govbr-auth
```

Instalação com framework específico:
```bash
pip install govbr-auth[fastapi]
# ou
pip install govbr-auth[flask]
# ou
pip install govbr-auth[django]
```

Instalação completa (todos os frameworks):
```bash
pip install govbr-auth[full]
```

## ⚙️ Configuração

Via `.env`:
```env
GOVBR_REDIRECT_URI=
GOVBR_CLIENT_ID=
GOVBR_CLIENT_SECRET=
GOVBR_CODE_CHALLENGE_METHOD=S256
GOVBR_SCOPE=openid email profile
GOVBR_RESPONSE_TYPE=code
CRIPT_VERIFIER_SECRET=
GOVBR_AUTH_URL=https://sso.staging.acesso.gov.br/authorize
GOVBR_TOKEN_URL=https://sso.staging.acesso.gov.br/token
GOVBR_USER_INFO=https://api.acesso.gov.br/userinfo
JWT_SECRET=chave_super_secreta
JWT_EXPIRES_MINUTES=60
JWT_ALGORITHM=HS256
```

Ou via código:
```python
from govbr_auth.core.config import GovBrConfig

config = GovBrConfig(
        client_id="...",
        client_secret="...",
        redirect_uri="https://...",
        cript_verifier_secret="...",
        auth_url_path="/login/govbr",
        callback_url_path="/login/govbr/retorno"
)
```

## 🧩 Uso com FastAPI
```python
from fastapi import FastAPI
from govbr_auth.controller import GovBrConnector

app = FastAPI()
connector = GovBrConnector(config,
                           prefix="/auth",
                           authorize_endpoint="/govbr/authorize",
                           authenticate_endpoint="/govbr/callback",
                           )
connector.init_fastapi(app)
```

## 🌐 Uso com Flask
```python
from flask import Flask
from govbr_auth.controller import GovBrConnector

app = Flask(__name__)
connector = GovBrConnector(config,
                           prefix="/auth",
                           authorize_endpoint="/govbr/authorize",
                           authenticate_endpoint="/govbr/callback",
                           )
connector.init_flask(app)
```

## 🛠️ Uso com Django
```python
from govbr_auth.controller import GovBrConnector

connector = GovBrConnector(config,
                           prefix="/auth",
                           authorize_endpoint="/govbr/authorize",
                           authenticate_endpoint="/govbr/callback",
                           )

urlpatterns = [
    *connector.init_django(),
]
```

## 🧱 Uso com Stack Personalizada (baixo nível)
Você pode usar os serviços principais diretamente, de forma **assíncrona ou síncrona**:

### Async
```python
from govbr_auth.core.govbr import GovBrAuthorize, GovBrIntegration

authorize = GovBrAuthorize(config)
auth_url = authorize.build_authorize_url()

integration = GovBrIntegration(config)
result = await integration.async_exchange_code_for_token(code, state)
```

### Sync
```python
from govbr_auth.core.govbr import GovBrAuthorize, GovBrIntegration

authorize = GovBrAuthorize(config)
auth_url = authorize.build_authorize_url_sync()

integration = GovBrIntegration(config)
result = integration.exchange_code_for_token_sync(code, state)
```

Ideal para:
- APIs customizadas
- Serviços Lambda/FaaS
- Apps que não usam frameworks web tradicionais

## 📌 Endpoints Disponíveis (padrão)

- `GET /auth/govbr/authorize` → Retorna a URL de autorização Gov.br com PKCE
- `GET /auth/govbr/authenticate` → Recebe `code` e `state`, troca por tokens e retorna dados decodificados

> Os caminhos podem ser personalizados via `GovBrConfig`

## ✅ Testes
```bash
pytest tests/
```

## 📄 Licença
MIT

---

Feito com 💙 para integrar com o Login Único Gov.br
