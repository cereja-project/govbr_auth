# govbr-auth

Autenticação Gov.br para Python com um core OAuth 2.0/OpenID Connect independente
de framework e adapters opcionais para FastAPI, Django e Flask.

O fluxo OAuth é stateless no backend: funciona com múltiplos workers, sem
armazenamento compartilhado, desde que todos usem a mesma secret
`GOVBR_TRANSACTION_SECRET`.

[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-0f766e.svg)](LICENSE)
[![FakeGov](https://img.shields.io/badge/FakeGov-local-0f766e.svg)](#teste-a-integração-sem-depender-do-govbr)

> [!IMPORTANT]
> Este é um projeto comunitário, sem manutenção, homologação ou endosso do
> Governo Federal. O FakeGov é um simulador local: use nele somente credenciais
> e dados pessoais fictícios. Essa restrição é exclusiva ao FakeGov; para uma
> integração real, configure a biblioteca com o provedor oficial.

## Teste a integração sem depender do Gov.br

**FakeGov** é um provedor OAuth/OIDC local incluído na biblioteca. Ele permite
desenvolver, demonstrar e testar o fluxo completo sem credenciais oficiais, sem
acesso à internet e sem alterar o código consumidor.

![Instalar, iniciar, entrar e concluir o fluxo local com FakeGov](https://raw.githubusercontent.com/cereja-project/govbr_auth/main/docs/media/fakegov-flow.svg)

**Instalar → Iniciar → Entrar → Concluir.** O caminho demonstrativo exercita
o mesmo core de autenticação usado pelos adapters.

### Experimente localmente

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

Abra `http://localhost:8000`, clique em **Entrar com Gov.br** e use o CPF
`11122233344` com a senha `senha-ficticia`. O launcher escuta apenas em loopback e
não exibe CPF, senha, tokens ou segredos nas respostas.

## Use FakeGov na sua aplicação

O exemplo abaixo é copiável e executável em um diretório vazio.

```bash
pip install "govbr-auth[fastapi,fake]"
```

Crie `myapp.py`:

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

Crie usuários locais fictícios fora do Git:

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

Abra `http://127.0.0.1:8000/auth/govbr/login`, use CPF `11122233344` e
senha `senha-ficticia`, e conclua o callback. A resposta de exemplo renderiza
somente `{"authenticated": true}`; CPF, senha, tokens e segredos não são
exibidos em respostas HTTP.

Com `GOVBR_PROVIDER=fake`, a aplicação mantém o mesmo runtime consumidor e a
mesma fachada `GovBrAuth`: o modo fake troca apenas os endpoints do provedor e
o transporte HTTP interno (`FakeGovHttpTransport`). Para composições
avançadas, o simulador canônico é `govbr_auth.fake.FakeGovSimulator`, criado por
`govbr_auth.fake.create_fake_gov_simulator`.

No Django, inclua `auth.urlpatterns` no `urlpatterns` do projeto. No Flask,
registre os dois blueprints condicionais com `auth.register(app)`. Em ambos os
casos, o código do consumidor permanece o mesmo; só a configuração do provedor
é alterada.

Os exemplos completos de FastAPI, Django e Flask no
[guia de início rápido](https://govbr-auth.readthedocs.io/en/latest/guide/quick-start.html)
criam os arquivos da aplicação no diretório do usuário e funcionam após a
instalação do extra correspondente; não dependem de um checkout deste repositório.

## Instalação

Instale somente o core ou o extra correspondente à aplicação:

```bash
pip install govbr-auth                 # somente o core
pip install "govbr-auth[fastapi]"      # adapter FastAPI
pip install "govbr-auth[fastapi,fake]" # FastAPI + FakeGov + uvicorn
pip install "govbr-auth[django]"       # adapter Django
pip install "govbr-auth[flask]"        # adapter Flask
pip install "govbr-auth[fake]"         # launcher FakeGov
```

## Como a comunicação funciona

A aplicação expõe `/auth/govbr/login` e `/auth/govbr/callback`. Depois do
login, o backend troca o código no endpoint `token`, busca as chaves em `jwk`,
valida o ID Token e consulta `userinfo` antes de chamar `on_success`.

Com `GOVBR_PROVIDER=official`, essas chamadas vão para o Gov.br. Com
`GOVBR_PROVIDER=fake`, as rotas FakeGov são montadas no mesmo router e o
backend usa `FakeGovHttpTransport`. Em outras palavras: é o mesmo runtime
consumidor, e a configuração fake troca apenas os endpoints do provedor e o
transporte HTTP interno. O fluxo end-to-end do launcher também inclui a página
inicial. O diagrama completo está em
[`docs/guide/communication-flow.rst`](docs/guide/communication-flow.rst).

Para desenvolvimento, execute a aplicação com `GOVBR_PROVIDER=fake`. A mesma
fachada e as mesmas rotas do backend são usadas com o provedor oficial; somente
a composição selecionada pela configuração muda.

## Somente o provedor FakeGov

Sem `GOVBR_FAKE_END_TO_END=true`, `python -m govbr_auth.fake` inicia apenas o
provedor/login, sem a página inicial demonstrativa. Esse modo atende uma
aplicação local executada em outro processo; o servidor continua restrito a
loopback.

## Customizar usuários

Defina `GOVBR_FAKE_USERS_FILE` com um JSON fora do Git:

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

```json
{"users": [{"cpf": "11122233344", "password": "senha-ficticia", "name": "Usuário Fake", "email": "fake@example.test"}]}
```

O arquivo substitui os usuários defaults, é validado na inicialização e fica
em memória; não use credenciais reais. Para fontes próprias, implemente o
protocolo de repositório descrito no guia de FakeGov.

## Provedor oficial

Instale a biblioteca sem extras e configure `GOVBR_PROVIDER=official` (o
default), endpoints, credenciais, redirect e `GOVBR_TRANSACTION_SECRET`.
Gere uma vez o segredo:

```python
from govbr_auth import generate_transaction_secret

print(generate_transaction_secret())
```

Mantenha o valor secreto e use o mesmo valor em todas as instâncias. Não gere
uma chave nova a cada inicialização. O backend cifra e autentica com Fernet um
envelope de `state` com TTL, PKCE e nonce. O state não é um registro de uso
único: a prevenção de replay depende do authorization code de uso único
validado pelo provedor.

Esse desenho permite múltiplos workers sem armazenamento compartilhado; todos
precisam receber a mesma secret `GOVBR_TRANSACTION_SECRET`. Em produção, por
exemplo:

```bash
uvicorn myapp:app --workers 4
```

Consulte a [documentação](docs/index.rst) para configuração completa, solução
de problemas e uso avançado.

## Desenvolvimento

```bash
python -m pip install -r requirements-dev.txt
python -m pytest --tb=short --disable-warnings -q
```

## Licença

MIT. Consulte `LICENSE`.
