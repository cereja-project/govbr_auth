Início rápido
=============

O caminho curto para validar a integração é usar ``GOVBR_PROVIDER=fake``. O
mesmo adapter e o mesmo callback funcionam depois com o provedor oficial.

Aplicação FastAPI
-----------------

Instale o adapter e, para o fluxo local, o extra FakeGov::

    pip install "govbr-auth[fastapi,fake]"

Salve ``myapp.py``:

.. code-block:: python

    from pathlib import Path

    from dotenv import load_dotenv
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse

    from govbr_auth.fastapi import AuthContext, GovBrAuth
    from govbr_auth.runtime import GovBrRuntimeSettings

    async def authenticated(context: AuthContext) -> JSONResponse:
        return JSONResponse({"authenticated": True})

    load_dotenv(dotenv_path=Path.cwd() / ".env", override=False)
    settings = GovBrRuntimeSettings.from_environment()
    app = FastAPI()
    auth = GovBrAuth(settings=settings, on_success=authenticated)
    app.include_router(auth.router)

O adapter registra ``/auth/govbr/login`` e o callback. No modo fake, as rotas
do provedor são montadas no mesmo app; a página demo fica exclusivamente no
launcher ``python -m govbr_auth.fake``.

Aplicação Django
----------------

Instale::

    pip install "govbr-auth[django]"

Salve ``django_app.py``:

.. quickstart-django:start

.. code-block:: python

    from pathlib import Path

    from dotenv import load_dotenv
    from django.http import JsonResponse

    from govbr_auth.django import GovBrAuth
    from govbr_auth.runtime import GovBrRuntimeSettings

    SECRET_KEY = "fake-local-only"
    DEBUG = True
    ALLOWED_HOSTS = ["127.0.0.1"]
    ROOT_URLCONF = __name__

    def authenticated(context, request):
        return JsonResponse({"authenticated": True})

    load_dotenv(dotenv_path=Path.cwd() / ".env", override=False)
    settings = GovBrRuntimeSettings.from_environment()
    auth = GovBrAuth(settings=settings, on_success=authenticated)
    urlpatterns = auth.urlpatterns

.. quickstart-django:end

Execute com ``python -m django runserver 127.0.0.1:8000 --settings=django_app``.

Aplicação Flask
---------------

Instale::

    pip install "govbr-auth[flask]"

Salve ``flask_app.py``:

.. quickstart-flask:start

.. code-block:: python

    from pathlib import Path

    from dotenv import load_dotenv
    from flask import Flask, jsonify

    from govbr_auth.flask import GovBrAuth
    from govbr_auth.runtime import GovBrRuntimeSettings

    load_dotenv(dotenv_path=Path.cwd() / ".env", override=False)
    settings = GovBrRuntimeSettings.from_environment()
    app = Flask(__name__)

    def authenticated(context, request):
        return jsonify({"authenticated": True})

    auth = GovBrAuth(settings=settings, on_success=authenticated)
    auth.register(app)

.. quickstart-flask:end

Execute com ``flask --app flask_app:app run --port 5000``.

Testar com FakeGov
------------------

Crie um arquivo fictício ``fake-users.local.json`` e configure apenas:

.. code-block:: json

    {"users": [{"cpf": "11122233344", "password": "senha-ficticia", "name": "Usuário Fake", "email": "fake@example.test"}]}

.. code-block:: text

    GOVBR_PROVIDER=fake
    GOVBR_FAKE_USERS_FILE=./fake-users.local.json

No POSIX, use ``export GOVBR_FAKE_USERS_FILE="$PWD/fake-users.local.json"``;
no PowerShell, use ``$env:GOVBR_FAKE_USERS_FILE = "$PWD\fake-users.local.json"``.

Execute sua aplicação e abra ``/auth/govbr/login``. Para abrir a página visual
de demonstração e iniciar o fluxo completo em um launcher dedicado, execute::

    pip install "govbr-auth[fastapi,fake]"
    python -m govbr_auth.fake

O launcher publica ``/govbr-auth-demo`` em loopback e não deve ser exposto na
rede. Abra a página e clique em **Entrar com gov.br**. O FakeGov aceita somente
credenciais fictícias; não use credenciais reais. A página demo não é injetada nos adapters.

O backend é stateless, pode usar múltiplos workers sem armazenamento
compartilhado e exige a mesma secret ``GOVBR_TRANSACTION_SECRET`` em todas as
instâncias. Execute, por exemplo::

    uvicorn myapp:app --workers 4

Usar o provedor oficial
-----------------------

O valor padrão é ``GOVBR_PROVIDER=official``. Configure endpoints, credenciais,
``GOVBR_REDIRECT_URI`` e ``GOVBR_TRANSACTION_SECRET`` conforme
:doc:`configuration`. O mesmo código de aplicação permanece válido.

O backend usa ``state`` cifrado com Fernet, PKCE e nonce. O ``state`` não é um
registro de uso único; a proteção contra replay depende do authorization code
de uso único invalidado pelo provedor.

Customizar usuários do FakeGov
------------------------------

Defina ``GOVBR_FAKE_USERS_FILE`` com um JSON contendo ``users``. O arquivo deve
ficar fora do Git e conter apenas dados fictícios. Veja :doc:`fake-mode` para
repositórios próprios.
