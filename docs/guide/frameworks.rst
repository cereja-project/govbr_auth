🧩 Frameworks
===============

FastAPI
-------

.. code-block:: python

    from fastapi import FastAPI
    from govbr_auth import GovBrConnector, GovBrConfig

    config = GovBrConfig.from_env()

    def handle_auth_success(data, request):
        """Callback após autenticação bem-sucedida"""
        user = data["id_token_decoded"]
        return {
            "mensagem": "Login efetuado com sucesso!",
            "usuario": user["name"],
            "cpf": user["sub"]
        }

    app = FastAPI()

    connector = GovBrConnector(
        config,
        prefix="/auth/govbr",
        authorize_endpoint="authorize",
        authenticate_endpoint="authenticate",
        on_auth_success=handle_auth_success,
    )

    connector.init_fastapi(app)

    # Endpoints criados:
    # GET  /auth/govbr/authorize -> Retorna URL OAuth
    # POST /auth/govbr/authenticate -> Troca code+state por token

**Executar**::

    uvicorn seu_arquivo:app --reload

Flask
-----

.. code-block:: python

    from flask import Flask, jsonify
    from govbr_auth import GovBrConnector, GovBrConfig

    config = GovBrConfig.from_env()

    def handle_auth_success(data, request):
        """Callback após autenticação bem-sucedida"""
        user = data["id_token_decoded"]
        return jsonify({
            "mensagem": "Login efetuado com sucesso!",
            "usuario": user["name"],
            "cpf": user["sub"]
        })

    app = Flask(__name__)

    connector = GovBrConnector(
        config,
        prefix="/auth/govbr",
        authorize_endpoint="authorize",
        authenticate_endpoint="authenticate",
        on_auth_success=handle_auth_success,
    )

    connector.init_flask(app)

    # Endpoints criados:
    # GET  /auth/govbr/authorize -> Retorna URL OAuth
    # POST /auth/govbr/authenticate -> Troca code+state por token

**Executar**::

    flask run

Django
------

Em `urls.py`::

    from django.urls import path
    from govbr_auth import GovBrConnector, GovBrConfig

    config = GovBrConfig.from_env()

    def handle_auth_success(data, request):
        """Callback após autenticação bem-sucedida"""
        from django.http import JsonResponse
        user = data["id_token_decoded"]
        return JsonResponse({
            "mensagem": "Usuário autenticado!",
            "nome": user.get("name"),
            "cpf": user.get("sub")
        })

    connector = GovBrConnector(
        config,
        prefix="auth/govbr",
        authorize_endpoint="authorize",
        authenticate_endpoint="authenticate",
        on_auth_success=handle_auth_success,
    )

    urlpatterns = [
        *connector.init_django(),
    ]

    # Endpoints criados:
    # GET  auth/govbr/authorize -> Retorna URL OAuth
    # POST auth/govbr/authenticate -> Troca code+state por token

**Executar**::

    python manage.py runserver

Stack Personalizada
--------------------

Para frameworks não suportados ou APIs customizadas, use a API de baixo nível:

**Async**::

    from govbr_auth.core.govbr import GovBrAuthorize, GovBrIntegration

    authorize = GovBrAuthorize(config)
    auth_url_result = await authorize.build_authorize_url()

    integration = GovBrIntegration(config)
    result = await integration.async_exchange_code_for_token(code, state)

**Sync**::

    from govbr_auth.core.govbr import GovBrAuthorize, GovBrIntegration

    authorize = GovBrAuthorize(config)
    auth_url_result = authorize.build_authorize_url_sync()

    integration = GovBrIntegration(config)
    result = integration.exchange_code_for_token_sync(code, state)

Comparação de Frameworks
------------------------

.. list-table::
   :header-rows: 1

   * - Framework
     - Suportado
     - Async
     - Status Codes
     - Autenticação Fake
   * - FastAPI
     - ✅
     - ✅
     - 400/401
     - ✅ Automático
   * - Flask
     - ✅
     - ❌
     - 400/401
     - ✅ Automático
   * - Django
     - ✅
     - ❌
     - 400/401
     - Parcial
   * - Custom
     - ✅
     - ✅/❌
     - Você define
     - Manual

Callbacks de Sucesso
--------------------

O `on_auth_success` é chamado após autenticação bem-sucedida:

.. code-block:: python

    def on_auth_success(data, request):
        """
        Args:
            data: {
                "token": {raw token response},
                "id_token_decoded": {user claims}
            }
            request: Request object (FastAPI/Flask/Django)

        Returns:
            Qualquer coisa que seu framework aceita como resposta
        """
        user = data["id_token_decoded"]
        return {
            "status": "ok",
            "user_cpf": user["sub"],
            "user_name": user["name"],
            "user_email": user["email"],
        }

**Para FastAPI (async)**::

    async def on_auth_success(data, request):
        # Pode fazer operações async aqui
        user_id = data["id_token_decoded"]["sub"]
        await db.save_user(user_id)
        return {"status": "ok"}

Tratamento de Erros
--------------------

Os frameworks implementam tratamento automático:

- `GovBrException` → HTTP 400 (erro de configuração)
- `GovBrAuthenticationError` → HTTP 401 (erro de autenticação)

Customize com try/catch se precisar:

.. code-block:: python

    from govbr_auth import GovBrAuthenticationError

    try:
        result = await integration.async_exchange_code_for_token(code, state)
    except GovBrAuthenticationError as e:
        # Log, registre tentativa, etc
        return {"error": "Autenticação falhou"}

