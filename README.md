# govbr-auth

Biblioteca assíncrona para autenticação Gov.br em FastAPI. O núcleo de
composição é independente de framework; nesta versão, o adaptador público
disponível é o FastAPI.

Projeto comunitário, sem manutenção, homologação ou endosso do Governo Federal.

## Usar FakeGov no meu app

```bash
pip install "govbr-auth[fake]"
```

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
## Como a comunicação funciona

A aplicação expõe `/auth/govbr/login` e `/auth/govbr/callback`. Depois do
login, o backend troca o código no endpoint `token`, busca as chaves em `jwk`,
valida o ID Token e consulta `userinfo` antes de chamar `on_success`.

Com `GOVBR_PROVIDER=official`, essas chamadas vão para o Gov.br. Com
`GOVBR_PROVIDER=fake`, as rotas FakeGov são montadas no mesmo router e o
backend usa transporte ASGI em memória. O fluxo end-to-end do launcher também
inclui a página inicial. O diagrama completo está em
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

```json
{"users": [{"cpf": "12345678901", "password": "senha-ficticia", "name": "Usuário Fake", "email": "fake@example.test"}]}
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
