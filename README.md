<p align="left">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/cereja-project/govbr_auth/main/docs/media/govbr-auth-logo-light.svg">
    <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/cereja-project/govbr_auth/main/docs/media/govbr-auth-logo.svg">
    <img src="https://raw.githubusercontent.com/cereja-project/govbr_auth/main/docs/media/govbr-auth-logo.svg" alt="govbr-auth" width="320">
  </picture>
</p>

[![PyPI version](https://badge.fury.io/py/govbr-auth.svg)](https://badge.fury.io/py/govbr-auth)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-0f766e.svg)](LICENSE)
[![Core](https://img.shields.io/badge/Core-async%20OAuth%2FOIDC-0f766e.svg)](#instalação)
[![FakeGov](https://img.shields.io/badge/FakeGov-local-0f766e.svg)](#teste-a-integração-sem-depender-do-govbr)

# Autenticamente pythônica

Uma biblioteca moderna e robusta para integração com o Login Único gov.br. Seu *core* assíncrono OAuth 2.0/OpenID Connect é independente de framework e cuida das partes mais sensíveis do fluxo - PKCE, nonce, state criptografado, troca de tokens, validação de assinatura, claims do ID Token e consulta ao userinfo -, entregando para a aplicação uma API enxuta, segura e previsível. Adapters opcionais conectam esse mesmo *core* ao FastAPI, Django e Flask.

E como a cereja do bolo, o projeto inclui o **FakeGov**, um simulador para ambientes de desenvolvimento e teste que permite depurar o fluxo completo de autenticação antes da homologação oficial. Isso reduz dependências externas, acelera o setup e encurta o ciclo de desenvolvimento da equipe.

O fluxo OAuth é 100% *stateless* no backend: funciona com múltiplos *workers* e sem armazenamento compartilhado, bastando que todos utilizem a mesma secret `GOVBR_TRANSACTION_SECRET`.

> [!IMPORTANT]
> 1. Este é um projeto open source independente, sem manutenção, homologação ou endosso do Governo Federal.
> 2. O FakeGov é estritamente um simulador para testes end-to-end e desenvolvimento. Jamais o exponha em ambientes de produção.


## Índice

**Começar**

- [Instalação](#instalação)
- [Teste a integração sem depender do gov.br](#teste-a-integração-sem-depender-do-govbr)

**Referência**

- [Credenciais de teste](#credenciais-de-teste)
- [Variáveis de ambiente](#variáveis-de-ambiente)

**Aprofundar**

- [Como a comunicação funciona](#como-a-comunicação-funciona)
- [Customizar usuários](#customizar-usuários)
- [Provedor oficial](#provedor-oficial)
- [Desenvolvimento](#desenvolvimento)

## Instalação

Instale somente o core ou o extra correspondente à aplicação:

| Comando | Para quê |
| --- | --- |
| `pip install govbr-auth` | Somente o core |
| `pip install "govbr-auth[fastapi]"` | Adapter FastAPI |
| `pip install "govbr-auth[django]"` | Adapter Django |
| `pip install "govbr-auth[flask]"` | Adapter Flask |
| `pip install "govbr-auth[fastapi,fake]"` | FastAPI + FakeGov + uvicorn |

## Teste a integração sem depender do gov.br

**FakeGov** é um provedor OAuth/OIDC local incluído na biblioteca. Ele permite
desenvolver, demonstrar e testar o fluxo completo sem credenciais oficiais, sem
acesso à internet e sem alterar o código consumidor. O caminho principal começa
pela sua aplicação; as ferramentas isoladas do provedor permanecem disponíveis
no [guia completo](https://govbr-auth.readthedocs.io/en/latest/guide/quick-start.html).

![Instalar, iniciar, entrar e concluir o fluxo local com FakeGov](https://raw.githubusercontent.com/cereja-project/govbr_auth/main/docs/media/fakegov-flow.svg)

**Instalar → Configurar → Entrar → Concluir.** O exemplo abaixo é copiável,
executável em um diretório vazio e exercita o mesmo core usado com o provedor
oficial.

### 1. Crie a aplicação e o usuário fictício

```bash
pip install "govbr-auth[fastapi,fake]"
```

Salve este conteúdo como `fake-users.local.json`:

```json
{
  "users": [
    {
      "cpf": "11122233344",
      "password": "senha-ficticia",
      "name": "Usuário Fake",
      "email": "fake@example.test"
    }
  ]
}
```

Salve o bloco completo abaixo como `myapp.py`:

<!-- quickstart-fastapi:start -->
```python
from pathlib import Path

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from govbr_auth.fastapi import AuthContext, GovBrAuth
from govbr_auth.runtime import GovBrRuntimeSettings


load_dotenv(dotenv_path=Path.cwd() / ".env", override=False)


async def authenticated(context: AuthContext) -> JSONResponse:
    # context.user contém o perfil OIDC validado. Use o subject como vínculo
    # com a conta local e mantenha dados pessoais somente no backend.
    return JSONResponse({"authenticated": bool(context.user.subject)})


def create_app(settings: GovBrRuntimeSettings) -> FastAPI:
    application = FastAPI()
    auth = GovBrAuth(
        on_success=authenticated,
        settings=settings,
        expose_tokens=False,
    )
    application.include_router(auth.router)
    return application


settings = GovBrRuntimeSettings.from_environment()
app = create_app(settings)


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")
```
<!-- quickstart-fastapi:end -->

### 2. Escolha como configurar

Para carregar por variáveis de ambiente, crie `.env`. O `myapp.py` chama
`load_dotenv` e depois `GovBrRuntimeSettings.from_environment()`, portanto o
mesmo código funciona no terminal, em containers e em serviços que injetam
variáveis diretamente:

```dotenv
GOVBR_PROVIDER=fake
GOVBR_FAKE_USERS_FILE=./fake-users.local.json
```

Quando a aplicação ou os testes já possuem um sistema próprio de configuração,
substitua as duas linhas que criam `settings` e `app` no final de `myapp.py`
pela composição explícita abaixo. O restante da aplicação permanece igual:

<!-- settings-fake:start -->
```python
from govbr_auth.runtime import GovBrProvider

settings = GovBrRuntimeSettings(
    provider=GovBrProvider.FAKE,
    fake_users_file=Path("fake-users.local.json"),
)
app = create_app(settings)
```
<!-- settings-fake:end -->

Para configurar o provedor oficial diretamente, componha os endpoints validados
com `GovBrSettings`. Segredos continuam vindo do ambiente ou de um cofre, nunca
do código versionado:

<!-- settings-official:start -->
```python
from os import environ

from pydantic import SecretStr
from govbr_auth.core import GovBrSettings, ProviderEnvironment
from govbr_auth.runtime import GovBrProvider

settings = GovBrRuntimeSettings(
    provider=GovBrProvider.OFFICIAL,
    oauth=GovBrSettings(
        environment=ProviderEnvironment.STAGING,
        authorization_url="https://sso.staging.acesso.gov.br/authorize",
        token_url="https://sso.staging.acesso.gov.br/token",
        userinfo_url="https://sso.staging.acesso.gov.br/userinfo/",
        client_id=environ["GOVBR_CLIENT_ID"],
        client_secret=SecretStr(environ["GOVBR_CLIENT_SECRET"]),
        redirect_uri=environ["GOVBR_REDIRECT_URI"],
        transaction_secret=SecretStr(environ["GOVBR_TRANSACTION_SECRET"]),
        issuer="https://sso.staging.acesso.gov.br/",
        jwks_url="https://sso.staging.acesso.gov.br/jwk",
    ),
)
app = create_app(settings)
```
<!-- settings-official:end -->

### 3. Execute e use o resultado

```bash
python myapp.py
```

Abra `http://localhost:8000/auth/govbr/login`, entre com as
[credenciais de teste](#credenciais-de-teste) e conclua o callback. No FakeGov,
a tela exibe o botão **Entrar com gov.br**.

O callback `authenticated` recebe um `AuthContext` já validado:

| Valor | Uso esperado |
| --- | --- |
| `context.user` | Perfil OIDC tipado; use `subject` para localizar ou criar a conta local |
| `context.claims` | Claims imutáveis e validadas do ID Token para decisões no backend |
| `context.tokens` | `None` por padrão; só aparece com `expose_tokens=True` e nunca deve ser enviado ao navegador |

Nesse ponto, a aplicação pode criar sua sessão, emitir seu próprio cookie,
atualizar o perfil local ou redirecionar para uma área autenticada. O exemplo
responde somente `{"authenticated": true}`; CPF, senha, tokens e segredos não
são exibidos em respostas HTTP. O arquivo de usuários aceita apenas dados
fictícios: não use credenciais reais.

Para trocar o FakeGov pelo provedor oficial, mantenha `myapp.py` e altere apenas
`GOVBR_PROVIDER` e as variáveis oficiais descritas em
[Provedor oficial](#provedor-oficial). O FakeGov nunca funciona como fallback
automático.

### Outros frameworks

No Django, inclua `auth.urlpatterns` no `urlpatterns` do projeto. No Flask,
registre os dois blueprints condicionais com `auth.register(app)`. Em ambos os
casos, o código do consumidor permanece o mesmo; só a configuração do provedor
é alterada.

Os exemplos completos de FastAPI, Django e Flask no
[guia de início rápido](https://govbr-auth.readthedocs.io/en/latest/guide/quick-start.html)
criam os arquivos da aplicação no diretório do usuário e funcionam após a
instalação do extra correspondente; não dependem de um checkout deste repositório.

Com `GOVBR_PROVIDER=fake`, a aplicação mantém o mesmo runtime consumidor e a
mesma fachada `GovBrAuth`: o modo fake troca apenas os endpoints do provedor e
o transporte HTTP interno (`FakeGovHttpTransport`). Para composições avançadas,
o simulador canônico é `govbr_auth.fake.FakeGovSimulator`, criado por
`govbr_auth.fake.create_fake_gov_simulator`.

## Credenciais de teste

| Campo | Valor |
| --- | --- |
| CPF | `11122233344` |
| Senha | `senha-ficticia` |

> [!WARNING]
> Credenciais fictícias, válidas apenas no FakeGov local. Para trocá-las, veja
> [Customizar usuários](#customizar-usuários).

## Variáveis de ambiente

| Variável | Valores | Efeito |
| --- | --- | --- |
| `GOVBR_PROVIDER` | `official` (default), `fake` | Escolhe os endpoints do provedor e o transporte HTTP interno |
| `GOVBR_ENVIRONMENT` | `production`, `staging`, `local` | Identifica o ambiente do provedor; endpoints oficiais incompatíveis impedem a inicialização |
| `GOVBR_FAKE_USERS_FILE` | Caminho para um JSON fora do Git | Substitui os usuários defaults do FakeGov |
| `GOVBR_TRANSACTION_SECRET` | Segredo gerado uma única vez | Obrigatório no provedor oficial; o mesmo valor em todas as instâncias |

## Como a comunicação funciona

![Fluxo de autenticação OAuth/OIDC entre navegador, aplicação e provedor](https://raw.githubusercontent.com/cereja-project/govbr_auth/main/docs/media/authentication-sequence.svg)

A aplicação expõe `/auth/govbr/login`. Com o provedor oficial, a rota de
callback usa exatamente o caminho de `GOVBR_REDIRECT_URI`; por exemplo,
`https://api.example.com/oauth/govbr/retorno` registra
`/oauth/govbr/retorno`. No FakeGov, o callback permanece
`/auth/govbr/callback` por padrão. Depois do login, o backend troca o código no
endpoint `token`, busca as chaves em `jwk`, valida o ID Token e consulta
`userinfo` antes de chamar `on_success`.

Com `GOVBR_PROVIDER=official`, essas chamadas vão para o gov.br. Com
`GOVBR_PROVIDER=fake`, as rotas FakeGov são montadas no mesmo router e o
backend usa `FakeGovHttpTransport`. Em outras palavras: é o mesmo runtime
consumidor, e a configuração fake troca apenas os endpoints do provedor e o
transporte HTTP interno. O diagrama completo está no
[`guia de fluxo de comunicação`](https://govbr-auth.readthedocs.io/en/latest/guide/communication-flow.html).

`GOVBR_ENVIRONMENT` descreve o provedor acessado, não onde a aplicação roda.
Ao usar os hosts oficiais, `authorize`, `token`, `userinfo`, `issuer` e `jwk`
devem ser todos de produção ou todos de staging. O `GOVBR_REDIRECT_URI` é
independente dessa comparação e pode apontar para a aplicação local, desde que
use HTTPS quando não for loopback. Para usar um DNS de desenvolvimento,
termine o TLS em um proxy reverso e encaminhe para a aplicação HTTP no
loopback; a biblioteca não gerencia certificados nem inicia esse proxy.

Para desenvolvimento, execute a aplicação com `GOVBR_PROVIDER=fake`. A mesma
fachada e as mesmas rotas do backend são usadas com o provedor oficial; somente
a composição selecionada pela configuração muda.

## Customizar usuários

Defina `GOVBR_FAKE_USERS_FILE` com um JSON fora do Git, no formato:

```json
{"users": [{"cpf": "11122233344", "password": "senha-ficticia", "name": "Usuário Fake", "email": "fake@example.test"}]}
```

No POSIX:

```sh
cat > fake-users.local.json <<'JSON'
{"users": [{"cpf": "11122233344", "password": "senha-ficticia", "name": "Usuário Fake", "email": "fake@example.test"}]}
JSON
export GOVBR_FAKE_USERS_FILE="$PWD/fake-users.local.json"
```

No PowerShell:

```powershell
@'
{"users": [{"cpf": "11122233344", "password": "senha-ficticia", "name": "Usuário Fake", "email": "fake@example.test"}]}
'@ | Set-Content -Encoding UTF8 .\fake-users.local.json
$env:GOVBR_FAKE_USERS_FILE = "$PWD\fake-users.local.json"
```

O arquivo substitui os usuários defaults, é validado na inicialização e fica
em memória; não use credenciais reais. Para fontes próprias, implemente o
protocolo de repositório descrito no guia de FakeGov.

## Provedor oficial

### Configuração

Instale a biblioteca sem extras e configure `GOVBR_PROVIDER=official` (o
default), endpoints, credenciais, redirect e `GOVBR_TRANSACTION_SECRET`.
Gere uma vez o segredo:

```python
from govbr_auth import generate_transaction_secret

print(generate_transaction_secret())
```

Mantenha o valor secreto e use o mesmo valor em todas as instâncias. Não gere
uma chave nova a cada inicialização.

### Estado e replay

O backend cifra e autentica com Fernet um envelope de `state` com TTL, PKCE e
nonce. O state não é um registro de uso único: a prevenção de replay depende do
authorization code de uso único validado pelo provedor.

### Múltiplos workers

Esse desenho permite múltiplos workers sem armazenamento compartilhado; todos
precisam receber a mesma secret `GOVBR_TRANSACTION_SECRET`. Em produção, por
exemplo:

```bash
uvicorn myapp:app --workers 4
```

Consulte a [documentação](https://govbr-auth.readthedocs.io/en/latest/index.html) para configuração completa, solução
de problemas e uso avançado.

## Desenvolvimento

```bash
python -m pip install -r requirements-dev.txt
python -m pytest --tb=short --disable-warnings -q
```

## Licença

MIT. Consulte `LICENSE`.
