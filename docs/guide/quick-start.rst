Início rápido
=============

O caminho mais curto para validar a integração é começar pelo FakeGov. Depois,
use o mesmo código da aplicação com ``GOVBR_PROVIDER=official`` e os endpoints
oficiais configurados.

Aplicação FastAPI
-----------------

Instale o adapter FastAPI com o FakeGov local e o servidor usado neste guia::

    pip install "govbr-auth[fastapi,fake]"

Salve ``myapp.py`` com a fachada pública e inclua o router na aplicação:

.. code-block:: python

    from fastapi import FastAPI
    from fastapi.responses import JSONResponse
    from govbr_auth.fastapi import AuthContext, GovBrAuth

    app = FastAPI()

    async def authenticated(context: AuthContext):
        return JSONResponse({"authenticated": True})

    auth = GovBrAuth(on_success=authenticated)
    app.include_router(auth.router)

Essa aplicação não cria um cliente OAuth, uma rota de callback ou uma factory
do FakeGov manualmente. ``GovBrAuth`` compõe o runtime selecionado e publica
as rotas ``/auth/govbr/login`` e ``/auth/govbr/callback``. Com
``GOVBR_PROVIDER=fake``, o app continua usando o mesmo runtime consumidor; a
configuração fake troca apenas os endpoints do provedor e o transporte HTTP
interno (``FakeGovHttpTransport``). Para composição avançada, o simulador canônico é
``govbr_auth.fake.FakeGovSimulator``, criado por
``govbr_auth.fake.create_fake_gov_simulator``.

Aplicação Django
----------------

Instale o adapter Django; o provedor embutido não exige o launcher ASGI::

    pip install "govbr-auth[django]"

Salve ``django_app.py`` em um diretório vazio:

.. quickstart-django:start

.. code-block:: python

    from django.http import JsonResponse
    from govbr_auth.django import GovBrAuth

    SECRET_KEY = "fake-local-only"
    DEBUG = True
    ALLOWED_HOSTS = ["127.0.0.1"]
    ROOT_URLCONF = __name__

    def authenticated(context, request):
        return JsonResponse({"authenticated": True})

    auth = GovBrAuth(on_success=authenticated)
    urlpatterns = auth.urlpatterns

.. quickstart-django:end

Depois de criar ``fake-users.local.json`` como indicado abaixo, execute::

    $env:GOVBR_PROVIDER = "fake"
    $env:GOVBR_FAKE_USERS_FILE = "$PWD\fake-users.local.json"
    python -m django runserver 127.0.0.1:8000 --settings=django_app

Aplicação Flask
---------------

Instale o adapter Flask; o provedor embutido não exige o launcher ASGI::

    pip install "govbr-auth[flask]"

Salve ``flask_app.py`` em um diretório vazio:

.. quickstart-flask:start

.. code-block:: python

    from flask import Flask, jsonify
    from govbr_auth.flask import GovBrAuth

    app = Flask(__name__)

    def authenticated(context, request):
        return jsonify({"authenticated": True})

    auth = GovBrAuth(on_success=authenticated)
    auth.register(app)

.. quickstart-flask:end

Depois de criar ``fake-users.local.json``, execute::

    $env:GOVBR_PROVIDER = "fake"
    $env:GOVBR_FAKE_USERS_FILE = "$PWD\fake-users.local.json"
    $env:GOVBR_FAKE_PORT = "5000"
    flask --app flask_app:app run --port 5000

No fluxo fake, use somente credenciais fictícias configuradas para o ambiente
local. As respostas públicas do app e do launcher não exibem CPF, senha,
tokens ou segredos.

Testar com FakeGov
------------------

Crie usuários locais fictícios fora do Git e execute a sua aplicação.

No POSIX::

    cat > fake-users.local.json <<'JSON'
    {"users": [{"cpf": "11122233344", "password": "senha-ficticia", "name": "Usuário Fake", "email": "fake@example.test"}]}
    JSON
    export GOVBR_PROVIDER=fake
    export GOVBR_FAKE_USERS_FILE="$PWD/fake-users.local.json"
    uvicorn myapp:app --reload

No PowerShell::

    @'
    {"users": [{"cpf": "11122233344", "password": "senha-ficticia", "name": "Usuário Fake", "email": "fake@example.test"}]}
    '@ | Set-Content -Encoding UTF8 .\fake-users.local.json
    $env:GOVBR_PROVIDER = "fake"
    $env:GOVBR_FAKE_USERS_FILE = "$PWD\fake-users.local.json"
    uvicorn myapp:app --reload

Abra ``http://localhost:8000/auth/govbr/login``, use CPF ``11122233344`` e
senha ``senha-ficticia``. O navegador será redirecionado para as rotas FakeGov
montadas na própria aplicação. O backend troca o código, busca JWKS e consulta
``userinfo`` usando ``FakeGovHttpTransport``. O callback retorna somente
``{"authenticated": true}``; CPF, senha, tokens e segredos não são exibidos em
respostas HTTP. Veja :doc:`communication-flow` para o diagrama completo.

Executar o launcher end-to-end
------------------------------

Para experimentar página inicial, aplicação e FakeGov em um único processo:

Instale o launcher::

    pip install "govbr-auth[fake]"

No POSIX::

    GOVBR_FAKE_END_TO_END=true python -m govbr_auth.fake

No PowerShell::

    $env:GOVBR_FAKE_END_TO_END = "true"
    python -m govbr_auth.fake

Abra ``http://localhost:8000``, clique em **Entrar com gov.br** e informe um
usuário fictício. O launcher é uma demonstração local; aplicações reais
usam ``GovBrAuth`` diretamente e preservam o mesmo runtime consumidor.

Para remover a variável da sessão após o teste no PowerShell::

    Remove-Item Env:GOVBR_FAKE_END_TO_END

Somente o servidor FakeGov
---------------------------

Sem a variável end-to-end, o launcher publica apenas o provedor local::

    python -m govbr_auth.fake

Esse perfil não possui página inicial em ``/`` e atende aplicações web próprias
que precisam apontar para um provedor local.

Usar o provedor oficial
-----------------------

O valor padrão é ``GOVBR_PROVIDER=official``. O ``GOVBR_REDIRECT_URI`` deve
apontar para o callback da API, por exemplo
``https://api.example.com/auth/govbr/callback``. Configure client ID, segredo,
redirect URI, endpoints OAuth/OIDC e ``GOVBR_TRANSACTION_SECRET`` conforme
:doc:`configuration`, então execute a mesma aplicação FastAPI. O fluxo de
login permanece igual; somente o runtime passa a conversar com o Gov.br
oficial. O FakeGov não é fallback automático.

O backend pode ser executado com múltiplos workers sem armazenamento
compartilhado. Configure a mesma secret ``GOVBR_TRANSACTION_SECRET`` em todos
eles e, em produção, execute por exemplo::

    uvicorn myapp:app --workers 4

O ``state`` é um envelope Fernet com TTL, PKCE e nonce, e não é um registro de
uso único. A proteção contra replay depende do authorization code de uso único
rejeitado pelo provedor após a primeira troca.

Customizar usuários do FakeGov
------------------------------

Defina ``GOVBR_FAKE_USERS_FILE`` com um JSON fora do Git:

No POSIX::

    cat > fake-users.local.json <<'JSON'
    {"users": [{"cpf": "11122233344", "password": "senha-ficticia", "name": "Usuário Fake", "email": "fake@example.test"}]}
    JSON
    export GOVBR_FAKE_USERS_FILE="$PWD/fake-users.local.json"

No PowerShell::

    @'
    {"users": [{"cpf": "11122233344", "password": "senha-ficticia", "name": "Usuário Fake", "email": "fake@example.test"}]}
    '@ | Set-Content -Encoding UTF8 .\fake-users.local.json
    $env:GOVBR_FAKE_USERS_FILE = "$PWD\fake-users.local.json"

O arquivo substitui os defaults; não use credenciais reais e mantenha-o fora
do Git. Veja :doc:`fake-mode` para validação e repositórios próprios.
