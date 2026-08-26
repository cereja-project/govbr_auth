FakeGov local
=============

O FakeGov é um simulador local do provedor OAuth 2.0/OpenID Connect Gov.br.
Ele não é o frontend da aplicação consumidora: seu papel é responder às
interações de autorização, emissão de tokens, JWKS e ``userinfo`` como um
Gov.br controlado para desenvolvimento, testes e demonstrações.

A aplicação consumidora continua tendo seu próprio frontend e sua própria API.
A API usa ``govbr_auth`` no backend; o frontend chama a API, e a API inicia e
conclui o fluxo OAuth. A tela HTML de login do FakeGov existe somente porque o
protocolo OAuth redireciona o navegador para a interface do provedor.

A mesma fachada e as mesmas rotas do backend são usadas com o provedor oficial;
somente a composição selecionada pela configuração muda.

Usar FakeGov no meu app
-----------------------

Instale o extra exato para o adapter e o fluxo que você vai executar::

    pip install "govbr-auth[fastapi,fake]"   # FastAPI com rotas fake locais e launcher
    pip install "govbr-auth[django]"         # Django com provedor fake montado no app
    pip install "govbr-auth[flask]"          # Flask com provedor fake montado no app

Monte a fachada do adaptador na API:

.. code-block:: python

    from fastapi import FastAPI
    from govbr_auth.fastapi import AuthContext, GovBrAuth

    app = FastAPI()

    async def authenticated(context: AuthContext):
        return {"authenticated": True, "subject": context.user.sub}

    auth = GovBrAuth(on_success=authenticated)
    app.include_router(auth.router)

Inicie a API com ``GOVBR_PROVIDER=fake``. O frontend da aplicação continua
chamando a API normalmente. A biblioteca monta as rotas do FakeGov junto ao
adaptador e usa transporte ASGI em memória para as chamadas de backend; o
código da aplicação não precisa criar factories do provedor. O app continua no
mesmo runtime consumidor; a configuração fake troca apenas os endpoints do
provedor e o transporte HTTP interno.

Para os adapters síncronos suportados, mantenha a mesma lógica de consumo e
troque apenas o extra de instalação e a montagem do adapter:

- Django: ``from govbr_auth.django import GovBrAuth`` e ``urlpatterns = auth.urlpatterns``
- Flask: ``from govbr_auth.flask import GovBrAuth`` e ``auth.register(app)``

O fluxo completo entre frontend, API, FakeGov e runtime está em
:doc:`communication-flow`.

Executar end-to-end
-------------------------

O launcher é uma conveniência para demonstrar o fluxo sem uma aplicação
frontend separada. Ele cria uma página inicial de demonstração, a API do
consumidor e o FakeGov no mesmo processo. Essa página inicial não transforma o
FakeGov em frontend: ela apenas substitui temporariamente o frontend real para
permitir um teste manual imediato.

No POSIX::

    GOVBR_FAKE_END_TO_END=true python -m govbr_auth.fake

No PowerShell::

    $env:GOVBR_FAKE_END_TO_END = "true"
    python -m govbr_auth.fake

Abra ``http://localhost:8000`` e complete o login. Para publicar somente o
servidor/provedor FakeGov, sem a página inicial de demonstração::

    python -m govbr_auth.fake

Esse perfil continua limitado a loopback. Portanto, a versão atual não deve
ser tratada como um serviço FakeGov compartilhado entre máquinas.

FakeGov compartilhado
---------------------

Um ambiente compartilhado para desenvolvedores ou testadores é uma evolução
natural do simulador: a API de cada ambiente poderia apontar para um FakeGov
central com usuários, chaves e dados de teste controlados. Isso exige um modo
de implantação explícito, com host não-loopback opt-in, autenticação de
administração, isolamento de dados, rotação de chaves e política para replay.

A implementação atual mantém o launcher em loopback e não oferece esse modo
remoto. Não remova essa restrição alterando apenas ``GOVBR_FAKE_HOST`` sem
revisar essas garantias.

Customizar usuários
-------------------

Os usuários fictícios default tornam o primeiro fluxo executável. Para
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

Para persistência própria, implemente o protocolo público
``govbr_auth.fake.FakeUserRepository``. O repositório deve fornecer
identidades e verificar credenciais sem expor senhas. Use hashes apropriados
em fontes persistentes. ``InMemoryFakeUserRepository`` e
``JsonFakeUserRepository`` são implementações prontas.

Responsabilidades
-----------------

``govbr_auth`` / API consumidora
    Mantém ``state``, PKCE e transações, troca o código, valida o ID Token,
    consulta ``userinfo`` e entrega o resultado ao frontend da aplicação.

FakeGov
    Simula o provedor OAuth/OIDC: autorização, login de usuário de teste,
    emissão de tokens, JWKS e ``userinfo``. Não substitui a API nem o frontend
    da aplicação.

Core
    Mantém as regras de segurança e validação do fluxo, independentemente de
    o transporte apontar para o Gov.br ou para o FakeGov.

Uso avançado
------------

``GovBrRuntimeSettings`` e ``create_govbr_runtime`` formam o núcleo neutro de
framework. ``create_fake_gov_simulator`` cria o grafo canônico do simulador.
As factories ``create_fake_govbr_router`` e ``create_fake_govbr_app`` atendem
topologias ASGI avançadas.

Os adapters públicos desta versão são FastAPI, Django e Flask. O store em memória rejeita replay
de authorization code apenas na mesma instância; distribuição entre
processos exige um store compartilhado fornecido pela aplicação.
