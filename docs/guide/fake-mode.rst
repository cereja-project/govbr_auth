FakeGov local
=============

O FakeGov é um provedor OAuth/OpenID Connect local. Ele nunca é fallback do
provedor oficial e escuta somente em loopback.

Usar FakeGov no meu app
-----------------------

Instale::

    pip install "govbr-auth[fake]"

Monte a fachada do adaptador:

.. code-block:: python

    from fastapi import FastAPI
    from govbr_auth.fastapi import AuthContext, GovBrAuth

    app = FastAPI()
    auth = GovBrAuth(on_success=authenticated)
    app.include_router(auth.router)

Inicie seu app com ``GOVBR_PROVIDER=fake``. A biblioteca compõe backend e
FakeGov sem duplicar factories no código do usuário.

Executar end-to-end
-------------------

Para iniciar frontend, backend e FakeGov no mesmo processo::

    GOVBR_FAKE_END_TO_END=true
    python -m govbr_auth.fake

Abra ``http://localhost:8000``. Para usar somente a tela de login/provedor,
execute sem a variável end-to-end::

    python -m govbr_auth.fake

Customizar usuários
-------------------

Os usuários fictícios defaults tornam o primeiro fluxo executável. Para
substituí-los, defina ``GOVBR_FAKE_USERS_FILE``:

.. code-block:: json

   {
     "users": [
       {
         "cpf": "12345678901",
         "password": "senha-ficticia",
         "name": "Usuário Fake",
         "email": "fake@example.test"
       }
     ]
   }

O arquivo é carregado na inicialização, exige ao menos um usuário, CPF com 11
dígitos e CPFs únicos. JSON inválido, campos extras e campos ausentes são
rejeitados; não use credenciais reais e mantenha o arquivo fora do Git.

Para persistência própria, implemente ``FakeUserRepository``. O repositório
deve fornecer identidades e verificar credenciais sem expor senhas. Use hashes
apropriados em fontes persistentes. ``InMemoryFakeUserRepository`` e
``JsonFakeUserRepository`` são implementações prontas.

Uso avançado
------------

``GovBrRuntimeSettings`` e ``create_govbr_runtime`` formam o núcleo neutro de
framework. ``create_fake_govbr_runtime`` cria o grafo canônico do provedor. As
factories ``create_fake_govbr_router`` e ``create_fake_govbr_app`` atendem
topologias separadas e integrações ASGI avançadas.

O adaptador público desta versão é FastAPI. O limite do núcleo está preparado
para adaptadores Django e Flask futuros, mas esses adaptadores ainda não são
suportados.

O store em memória rejeita replay de authorization code apenas na mesma
instância. Distribuição entre processos exige um store compartilhado fornecido
pela aplicação.
