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

Uma biblioteca autenticamente pythônica para integração com o Login Único gov.br. Seu core assíncrono OAuth 2.0/OpenID Connect é independente de framework e cuida das partes sensíveis do fluxo - PKCE, nonce, state criptografado e stateless, troca de tokens, validação de assinatura e claims do ID Token e consulta ao userinfo - deixando para a aplicação uma API menor, segura e previsível. Adapters opcionais integram esse mesmo core ao FastAPI, Django e Flask.

Inclui o FakeGov, um simulador local que permite desenvolver, testar e depurar o fluxo completo de autenticação antes da homologação oficial, reduzindo dependências externas, acelerando o setup do ambiente e encurtando o ciclo de desenvolvimento.

O fluxo OAuth é stateless no backend: funciona com múltiplos workers, sem
armazenamento compartilhado, desde que todos usem a mesma secret
`GOVBR_TRANSACTION_SECRET`.


> [!IMPORTANT]
> 1. Este é um projeto open source independente, sem manutenção, homologação ou
> endosso do Governo Federal.
> 
> 2. O FakeGov é um simulador para testes end-to-end, não o utilize para além deste propósito.

## Índice

**Começar**

- [Instalação](#instalação)
- [Teste a integração sem depender do gov.br](#teste-a-integração-sem-depender-do-govbr)
- [Use FakeGov na sua aplicação](#use-fakegov-na-sua-aplicação)

**Referência**

- [Credenciais de teste](#credenciais-de-teste)
- [Variáveis de ambiente](#variáveis-de-ambiente)
- [URLs por modo de execução](#urls-por-modo-de-execução)

**Aprofundar**

- [Como a comunicação funciona](#como-a-comunicação-funciona)
- [Somente o provedor FakeGov](#somente-o-provedor-fakegov)
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
| `pip install "govbr-auth[fake]"` | Launcher FakeGov |
| `pip install "govbr-auth[fastapi,fake]"` | FastAPI + FakeGov + uvicorn |

## Teste a integração sem depender do gov.br

**FakeGov** é um provedor OAuth/OIDC local incluído na biblioteca. Ele permite
desenvolver, demonstrar e testar o fluxo completo sem credenciais oficiais, sem
acesso à internet e sem alterar o código consumidor.

![Instalar, iniciar, entrar e concluir o fluxo local com FakeGov](https://raw.githubusercontent.com/cereja-project/govbr_auth/main/docs/media/fakegov-flow.svg)

**Instalar → Iniciar → Entrar → Concluir.** O caminho demonstrativo exercita
o mesmo core de autenticação usado pelos adapters.

### 1. Inicie o launcher

No POSIX:

```sh
pip install "govbr-auth[fake]"
cat > fake-users.local.json <<'JSON'
{"users": [{"cpf": "11122233344", "password": "senha-ficticia", "name": "Usuário Fake", "email": "fake@example.test"}]}
JSON
GOVBR_FAKE_USERS_FILE="$PWD/fake-users.local.json" GOVBR_FAKE_END_TO_END=true python -m govbr_auth.fake
```

No PowerShell:

```powershell
pip install "govbr-auth[fake]"
@'
{"users": [{"cpf": "11122233344", "password": "senha-ficticia", "name": "Usuário Fake", "email": "fake@example.test"}]}
'@ | Set-Content -Encoding UTF8 .\fake-users.local.json
$env:GOVBR_FAKE_USERS_FILE = "$PWD\fake-users.local.json"
$env:GOVBR_FAKE_END_TO_END = "true"
python -m govbr_auth.fake
```

### 2. Entre no fluxo

Abra `http://localhost:8000`, clique em **Entrar com gov.br** e use as
[credenciais de teste](#credenciais-de-teste).

O launcher escuta apenas em loopback e não exibe CPF, senha, tokens ou segredos
nas respostas.

## Use FakeGov na sua aplicação

O exemplo abaixo é copiável e executável em um diretório vazio.

### 1. Instale e crie `myapp.py`

```bash
pip install "govbr-auth[fastapi,fake]"
```

<!-- quickstart-fastapi:start -->
```python
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from govbr_auth.fastapi import AuthContext, GovBrAuth

app = FastAPI()

async def authenticated(context: AuthContext):
    return JSONResponse({"authenticated": True})

auth = GovBrAuth(on_success=authenticated)
app.include_router(auth.router)
```
<!-- quickstart-fastapi:end -->

### 2. Crie usuários fictícios e execute

No POSIX:

```sh
cat > fake-users.local.json <<'JSON'
{"users": [{"cpf": "11122233344", "password": "senha-ficticia", "name": "Usuário Fake", "email": "fake@example.test"}]}
JSON
export GOVBR_PROVIDER=fake
export GOVBR_FAKE_USERS_FILE="$PWD/fake-users.local.json"
uvicorn myapp:app --reload
```

No PowerShell:

```powershell
@'
{"users": [{"cpf": "11122233344", "password": "senha-ficticia", "name": "Usuário Fake", "email": "fake@example.test"}]}
'@ | Set-Content -Encoding UTF8 .\fake-users.local.json
$env:GOVBR_PROVIDER = "fake"
$env:GOVBR_FAKE_USERS_FILE = "$PWD\fake-users.local.json"
uvicorn myapp:app --reload
```

### 3. Conclua o callback

Abra `http://localhost:8000/auth/govbr/login`, entre com as
[credenciais de teste](#credenciais-de-teste) e conclua o callback. A resposta
de exemplo renderiza somente `{"authenticated": true}`; CPF, senha, tokens e
segredos não são exibidos em respostas HTTP.

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
o transporte HTTP interno (`FakeGovHttpTransport`). Para composições
avançadas, o simulador canônico é `govbr_auth.fake.FakeGovSimulator`, criado por
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
| `GOVBR_FAKE_USERS_FILE` | Caminho para um JSON fora do Git | Substitui os usuários defaults do FakeGov |
| `GOVBR_FAKE_END_TO_END` | `true` | Inclui a página inicial demonstrativa no launcher |
| `GOVBR_TRANSACTION_SECRET` | Segredo gerado uma única vez | Obrigatório no provedor oficial; o mesmo valor em todas as instâncias |

## URLs por modo de execução

| Modo | URL de entrada | O que é servido |
| --- | --- | --- |
| Launcher end-to-end (`GOVBR_FAKE_END_TO_END=true`) | `http://localhost:8000` | Página inicial demonstrativa mais provedor/login |
| Aplicação com `GOVBR_PROVIDER=fake` | `http://localhost:8000/auth/govbr/login` | Rotas do adapter: `/auth/govbr/login` e `/auth/govbr/callback` |
| Somente provedor FakeGov | Sem entrada direta | Endpoints do provedor: `/authorize`, `/login`, `/token`, `/userinfo` e `/jwk` |

> [!NOTE]
> No modo provider-only, `/` não é registrado. Abrir a raiz retorna 404; o
> ponto de entrada é a aplicação consumidora executada em outro processo.

## Como a comunicação funciona

A aplicação expõe `/auth/govbr/login` e `/auth/govbr/callback`. Depois do
login, o backend troca o código no endpoint `token`, busca as chaves em `jwk`,
valida o ID Token e consulta `userinfo` antes de chamar `on_success`.

Com `GOVBR_PROVIDER=official`, essas chamadas vão para o gov.br. Com
`GOVBR_PROVIDER=fake`, as rotas FakeGov são montadas no mesmo router e o
backend usa `FakeGovHttpTransport`. Em outras palavras: é o mesmo runtime
consumidor, e a configuração fake troca apenas os endpoints do provedor e o
transporte HTTP interno. O fluxo end-to-end do launcher também inclui a página
inicial. O diagrama completo está no
[`guia de fluxo de comunicação`](https://govbr-auth.readthedocs.io/en/latest/guide/communication-flow.html).

Para desenvolvimento, execute a aplicação com `GOVBR_PROVIDER=fake`. A mesma
fachada e as mesmas rotas do backend são usadas com o provedor oficial; somente
a composição selecionada pela configuração muda.

## Somente o provedor FakeGov

Sem `GOVBR_FAKE_END_TO_END=true`, `python -m govbr_auth.fake` inicia apenas o
provedor/login, sem a página inicial demonstrativa. Esse modo atende uma
aplicação local executada em outro processo; o servidor continua restrito a
loopback.

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
