Início rápido
=============

O caminho mais curto para validar a integração é começar pelo FakeGov. Depois,
use o mesmo código da aplicação com ``GOVBR_PROVIDER=official`` e os endpoints
oficiais configurados.

Aplicação FastAPI
-----------------

Instale a biblioteca com o extra do FakeGov para desenvolvimento::

    pip install "govbr-auth[fake]"

Monte a fachada pública e inclua o router na aplicação:

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
as rotas ``/auth/govbr/login`` e ``/auth/govbr/callback``.

Aplicação Django
----------------

Instale o adapter correspondente e inclua as URLs na aplicação Django::

    pip install "govbr-auth[django]"

.. code-block:: python

    from django.http import JsonResponse
    from govbr_auth.django import GovBrAuth

    def authenticated(context, request):
        return JsonResponse({"authenticated": True})

    auth = GovBrAuth(on_success=authenticated)
    urlpatterns = auth.urlpatterns

Para iniciar este exemplo em modo fake, a partir da raiz do repositório::

    $env:GOVBR_PROVIDER = "fake"
    $env:GOVBR_FAKE_END_TO_END = "true"
    python -m django runserver 127.0.0.1:8000 --settings=examples.django_settings

Aplicação Flask
---------------

No Flask, registre o adapter na aplicação hospedeira::

    pip install "govbr-auth[flask]"

.. code-block:: python

    from flask import Flask, jsonify
    from govbr_auth.flask import GovBrAuth

    app = Flask(__name__)

    def authenticated(context, request):
        return jsonify({"authenticated": True})

    auth = GovBrAuth(on_success=authenticated)
    auth.register(app)

Inicie o exemplo em modo fake::

    $env:GOVBR_PROVIDER = "fake"
    $env:GOVBR_FAKE_END_TO_END = "true"
    $env:GOVBR_FAKE_PORT = "5000"
    flask --app examples.example_flask:create_app run --port 5000

No fluxo fake, use somente credenciais fictícias configuradas para o ambiente
local; por exemplo, o usuário padrão ``12345678901`` com a senha
``ana-demo``. Esses valores ficam na documentação, não nas respostas da API.

Testar com FakeGov
------------------

Execute a sua aplicação com:

.. code-block:: console

    $env:GOVBR_PROVIDER = "fake"       # PowerShell
    uvicorn myapp:app --reload

No POSIX, use ``GOVBR_PROVIDER=fake uvicorn myapp:app --reload``. O navegador
será redirecionado para as rotas FakeGov montadas na própria aplicação. O
backend troca o código, busca JWKS e consulta ``userinfo`` usando transporte
ASGI em memória. Veja :doc:`communication-flow` para o diagrama completo.

Executar o launcher end-to-end
------------------------------

Para experimentar página inicial, aplicação e FakeGov em um único processo:

No POSIX::

    GOVBR_FAKE_END_TO_END=true python -m govbr_auth.fake

No PowerShell::

    $env:GOVBR_FAKE_END_TO_END = "true"
    python -m govbr_auth.fake

Abra ``http://localhost:8000``, clique em **Entrar com Gov.br** e informe um
usuário fictício. O launcher é uma demonstração local; aplicações reais
usam ``GovBrAuth`` diretamente.

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

Customizar usuários do FakeGov
------------------------------

Defina ``GOVBR_FAKE_USERS_FILE`` com um JSON como
``{"users": [{"cpf": "12345678901", "password": "senha-ficticia", "name": "Usuário Fake", "email": "fake@example.test"}]}``.
O arquivo substitui os defaults; não use credenciais reais e mantenha-o fora
do Git. Veja :doc:`fake-mode` para validação e repositórios próprios.
