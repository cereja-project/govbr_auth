FakeGov local
=============

O FakeGov é um simulador local do provedor OAuth 2.0/OpenID Connect Gov.br.
Ele responde autorização, emissão de tokens, JWKS e ``userinfo`` para
desenvolvimento e testes. Não é o frontend da aplicação consumidora.

Usar FakeGov na aplicação
-------------------------

Instale o extra do adapter e o FakeGov quando necessário::

    pip install "govbr-auth[fastapi,fake]"
    pip install "govbr-auth[django]"
    pip install "govbr-auth[flask]"

Monte o adapter normalmente:

.. code-block:: python

    from pathlib import Path

    from dotenv import load_dotenv
    from fastapi import FastAPI
    from govbr_auth.fastapi import AuthContext, GovBrAuth
    from govbr_auth.runtime import GovBrRuntimeSettings

    load_dotenv(dotenv_path=Path.cwd() / ".env", override=False)
    settings = GovBrRuntimeSettings.from_environment()
    app = FastAPI()

    async def authenticated(context: AuthContext):
        return {"authenticated": True, "subject": context.user.sub}

    auth = GovBrAuth(settings=settings, on_success=authenticated)
    app.include_router(auth.router)

Configure ``GOVBR_PROVIDER=fake`` e, opcionalmente,
``GOVBR_FAKE_USERS_FILE``. O adapter monta as rotas FakeGov na própria API e
usa ``FakeGovHttpTransport`` para as chamadas internas. A página visual demo
não é injetada nos adapters.

Launcher end-to-end
-------------------

Para executar o fluxo completo com a página de demonstração, use::

    python -m govbr_auth.fake

O launcher monta consumidor, FakeGov e a página demo na raiz ``/`` em loopback.
O caminho ``/govbr-auth-demo`` permanece disponível como alias. O launcher
não deve ser exposto na rede. A seleção fake é explícita no launcher, mas o
provedor nunca é fallback automático para uma aplicação oficial. O provedor
oficial permanece disponível na mesma aplicação com ``GOVBR_PROVIDER=official``.
O provedor oficial usa os endpoints oficiais configurados.

Customizar usuários
-------------------

Defina ``GOVBR_FAKE_USERS_FILE`` com um JSON no formato::

    {"users": [{"cpf": "11122233344", "password": "senha-ficticia", "name": "Usuário Fake", "email": "fake@example.test"}]}

Use somente credenciais fictícias; não use credenciais reais.

O arquivo é validado na inicialização, fica em memória e deve permanecer fora
do Git. Use somente credenciais fictícias.

No POSIX, use ``export GOVBR_FAKE_USERS_FILE="$PWD/fake-users.local.json"``. No
PowerShell, use ``$env:GOVBR_FAKE_USERS_FILE = "$PWD\fake-users.local.json"``.

FakeGov compartilhado
---------------------

O launcher atual é restrito a loopback. Um ambiente compartilhado exigiria
TLS, origem pública explícita, isolamento de usuários e tokens de teste,
rotação de chaves e controles administrativos. Não altere apenas
``GOVBR_FAKE_HOST`` para publicar o simulador.

Uso avançado
------------

``GovBrRuntimeSettings`` e ``create_govbr_runtime`` formam o núcleo neutro.
``create_fake_gov_simulator`` cria o simulador canônico. As factories
``create_fake_govbr_router`` e ``create_fake_govbr_app`` atendem topologias
ASGI que precisam somente do provedor.
