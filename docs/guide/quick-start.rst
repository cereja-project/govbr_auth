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
