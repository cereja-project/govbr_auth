⚡ Quick Start
===============

Instalação
----------

Instalação mínima (somente núcleo de serviços)::

    pip install govbr-auth

Instalação com framework específico::

    pip install govbr-auth[fastapi]
    # ou
    pip install govbr-auth[flask]
    # ou
    pip install govbr-auth[django]

Instalação completa (todos os frameworks)::

    pip install govbr-auth[full]

Exemplo Básico com FastAPI
---------------------------

.. code-block:: python

    from fastapi import FastAPI
    from govbr_auth import GovBrConfig, GovBrConnector, create_default_fake_users

    # Configuração para modo fake (desenvolvimento)
    config = GovBrConfig(
        client_id="fake-client-id",
        client_secret="fake-client-secret",
        redirect_uri="http://localhost:8000/auth/govbr/callback",
        cript_verifier_secret="Vvd9H5VC2Aqk-dwFOJX6MvQTuZZARmb37y7un9wkj0c=",
        govbr_auth_url="http://localhost:8000/fake-govbr/authorize",
        govbr_token_url="http://localhost:8000/fake-govbr/token",
        use_fake=True,
    )

    app = FastAPI()

    # Callback de sucesso
    def handle_success(data, request):
        user = data["id_token_decoded"]
        return {"mensagem": f"Bem-vindo, {user['name']}!", "cpf": user["sub"]}

    # Inicializa o connector (endpoints fake criados automaticamente!)
    connector = GovBrConnector(
        config=config,
        on_auth_success=handle_success,
        fake_users=create_default_fake_users()
    )
    connector.init_fastapi(app)

    # Executar: uvicorn seu_arquivo:app --reload
    # Acessar: http://localhost:8000/auth/govbr/authorize

Próximos Passos
---------------

1. Leia :doc:`configuration` para entender todas as opções
2. Escolha seu framework: :doc:`frameworks`
3. Para desenvolvimento, use :doc:`../guide/fake-mode` (modo fake)
4. Quando pronto para produção, confira :doc:`../guide/security-practices`

Exemplos
--------

Exemplos funcionais estão disponíveis em `examples/ <https://github.com/cereja-project/govbr_auth/tree/main/examples>`_ no repositório.

Executar exemplo com modo fake::

    USE_FAKE_GOVBR=true uvicorn examples.example_simple_app:app --reload

