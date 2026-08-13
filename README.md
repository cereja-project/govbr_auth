# govbr-auth

Biblioteca assíncrona para integrar autenticação Gov.br a aplicações FastAPI.
O cliente oficial valida state/PKCE, tokens RS256 por JWKS, issuer, audience,
nonce e vínculo de subject antes de entregar o usuário ao handler da aplicação.

## Requisitos e instalação

- Python 3.11+
- FastAPI

```bash
python -m pip install govbr-auth
```

O provedor local explícito é opcional:

```bash
python -m pip install "govbr-auth[fake]"
```

Para desenvolvimento do projeto:

```bash
python -m pip install -r requirements-dev.txt
python -m pytest --tb=short --disable-warnings -q
```

## Exemplo FastAPI

Configure endpoints e credenciais do provedor, além do segredo local usado pelo
consumidor para proteger suas transações:

```text
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
```

`GOVBR_TRANSACTION_SECRET` protege o `state`, nonce e PKCE mantidos pelo
consumidor. Ele não é uma credencial fornecida pelo Gov.br. Gere uma vez,
antes de preencher o `.env`:

```python
from govbr_auth import generate_transaction_secret

print(generate_transaction_secret())
```

Mantenha o valor secreto e use o mesmo valor em todas as instâncias do
deployment. Não gere uma chave nova a cada inicialização.

Execute o consumidor:

```bash
uvicorn examples.example_fastapi:create_app --factory
```

O arquivo `examples/example_fastapi.py` cria sempre o mesmo app consumidor. A
seleção do provedor ocorre exclusivamente pela configuração. O handler recebe
`AuthContext` com usuário e claims validados; tokens brutos só são incluídos
quando a aplicação opta explicitamente por `expose_tokens=True`.

## Fake Gov.br local

O fake nunca é ativado por flag nem por detecção de URL. Instale o extra
`[fake]`, configure URLs locais e inicie explicitamente o bootstrap de
desenvolvimento:

```bash
uvicorn examples.example_fastapi:create_development_app --factory
```

As factories e modelos do fake existem somente em `govbr_auth.fake`. O store de
replay em memória rejeita reutilização de authorization code apenas dentro da
mesma instância do fake. Instâncias distintas que compartilham as mesmas chaves
criptográficas não conseguem rejeitar globalmente um replay sem um store
compartilhado; esta distribuição não adiciona banco, Redis ou estado remoto.
Essa limitação pertence exclusivamente ao provedor fake local e não descreve
nem reduz garantias do provedor oficial Gov.br.

## Migração para a API v1

Esta versão remove Flask, Django, `GovBrConnector`, o core legado síncrono,
wrappers `build_authorize_url_sync` e `exchange_code_for_token_sync`, e a
ativação fake implícita. Migre para:

- `GovBrSettings`, `GovBrClient` e stores assíncronos em `govbr_auth.core`;
- `GovBrAuth` ou `create_govbr_router` em `govbr_auth`;
- factories explícitas do provedor local em `govbr_auth.fake`.

Não existe fallback fake no cliente oficial. Aplicações que precisam do fake
devem montá-lo explicitamente em um bootstrap separado.

## Licença

MIT. Consulte `LICENSE`.
