# govbr-auth

Engine de autenticação Gov.br independente de framework, com adapters oficiais
opcionais para FastAPI, Django e Flask. Instale somente o extra do framework
usado pela aplicação.

Projeto comunitário, sem manutenção, homologação ou endosso do Governo Federal.

## Instalação

```bash
pip install govbr-auth                 # somente a engine
pip install "govbr-auth[fastapi]"      # adapter FastAPI
pip install "govbr-auth[fastapi,fake]" # FastAPI + FakeGov local + uvicorn
pip install "govbr-auth[django]"       # adapter Django
pip install "govbr-auth[flask]"        # adapter Flask
pip install "govbr-auth[fake]"         # launcher FakeGov
```

## Usar FakeGov no meu app

```bash
pip install "govbr-auth[fastapi,fake]"
```

Crie `myapp.py`:

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

Para iniciar os exemplos locais em modo fake:

```powershell
# FastAPI
$env:GOVBR_PROVIDER = "fake"
uvicorn examples.example_fastapi:create_app --factory

# Django
$env:GOVBR_PROVIDER = "fake"
$env:GOVBR_FAKE_END_TO_END = "true"
python -m django runserver 127.0.0.1:8000 --settings=examples.django_settings

# Flask
$env:GOVBR_PROVIDER = "fake"
$env:GOVBR_FAKE_END_TO_END = "true"
$env:GOVBR_FAKE_PORT = "5000"
flask --app examples.example_flask:create_app run --port 5000
```

Abra `/auth/govbr/login` no app iniciado e conclua o callback autenticado com
credenciais locais configuradas para o simulador. As respostas renderizadas não
exibem CPF, senha, tokens ou segredos.

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

## Executar end-to-end

Para experimentar frontend, backend e login FakeGov no mesmo processo:

No POSIX:

```sh
pip install "govbr-auth[fake]"
GOVBR_FAKE_END_TO_END=true python -m govbr_auth.fake
```

No PowerShell:

```powershell
pip install "govbr-auth[fake]"
$env:GOVBR_FAKE_END_TO_END = "true"
python -m govbr_auth.fake
```

Abra `http://localhost:8000`. Sem `GOVBR_FAKE_END_TO_END=true`, o mesmo comando
`python -m govbr_auth.fake` inicia somente o provedor/login, sem página inicial.
O launcher escuta apenas em loopback.

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
uma chave nova a cada inicialização. Execute o exemplo com:

```bash
uvicorn examples.example_fastapi:create_app --factory
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
