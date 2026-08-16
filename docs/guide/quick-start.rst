Início rápido
=============

Executar end-to-end
-------------------

Instale o perfil local::

    pip install "govbr-auth[fake]"

Ative a composição completa e execute o único launcher::

    GOVBR_FAKE_END_TO_END=true
    python -m govbr_auth.fake

Abra ``http://localhost:8000``, clique em **Entrar com Gov.br**, informe um
usuário fictício e acompanhe o retorno validado ao backend.

Usar FakeGov no meu app
-----------------------

No FastAPI, a aplicação monta somente a fachada pública:

.. code-block:: python

    from fastapi import FastAPI
    from govbr_auth.fastapi import AuthContext, GovBrAuth

    app = FastAPI()

    async def authenticated(context: AuthContext):
        return {"subject": context.user.subject}

    auth = GovBrAuth(on_success=authenticated)
    app.include_router(auth.router)

Execute seu app com ``GOVBR_PROVIDER=fake`` no desenvolvimento. Para produção,
use o mesmo código com o provedor oficial configurado.

Customizar usuários
-------------------

Defina ``GOVBR_FAKE_USERS_FILE`` com um JSON como
``{"users": [{"cpf": "12345678901", "password": "senha-ficticia", "name": "Usuário Fake", "email": "fake@example.test"}]}``.
O arquivo substitui os defaults; não use credenciais reais e mantenha-o fora
do Git. Veja :doc:`fake-mode` para validação e repositórios próprios.

Somente o login FakeGov
-----------------------

Sem a variável end-to-end, o launcher publica apenas o provedor local::

    python -m govbr_auth.fake

Esse perfil não possui página inicial em ``/`` e atende aplicações web próprias.
