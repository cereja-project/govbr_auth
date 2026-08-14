Demo, fake e provedor oficial
==============================

================  ===============================  ==============================
Modo              Uso                              Entrada
================  ===============================  ==============================
``demo``          Avaliar a biblioteca sem código  ``python -m govbr_auth.demo``
``fake``          Integrar o provedor em uma app   ``govbr_auth.fake``
oficial           Homologação e produção           ``GovBrSettings`` + credenciais
================  ===============================  ==============================

A ``demo`` é uma demonstração empacotada: instale ``[demo]`` e execute o
comando da tabela para conhecer o fluxo em loopback. Ela não usa credenciais
Gov.br e não substitui a integração da sua aplicação.

Os comandos completos permanecem::

    pip install "govbr-auth[demo]"
    python -m govbr_auth.demo

O ``fake`` é um provedor OAuth/OpenID Connect explícito para desenvolvimento.
Seus símbolos existem somente em ``govbr_auth.fake`` e exigem o extra
``[fake]``. Ele não é fallback do cliente oficial e não é ativado por
configuração.

Use a factory pronta::

    uvicorn examples.example_fastapi:create_development_app --factory

Ela monta ``/fake-govbr/authorize``, ``/fake-govbr/token``,
``/fake-govbr/userinfo`` e ``/fake-govbr/jwk`` no mesmo ASGI de exemplo, mas
mantém a criação do consumidor e seu handler inalterados.

Usuários e credenciais
----------------------

A demo inclui usuários fictícios para o primeiro acesso. Para substituí-los,
defina ``GOVBR_FAKE_USERS_FILE`` com o caminho de um arquivo JSON neste formato
exato:

.. code-block:: json

   {
     "users": [
       {
         "cpf": "12345678901",
         "password": "senha-ficticia",
         "name": "Usuário Demo",
         "email": "demo@example.test"
       }
     ]
   }

O arquivo é carregado e validado durante a inicialização. A lista ``"users"``
deve conter pelo menos um item, cada ``"cpf"`` deve ter 11 dígitos e não pode
haver CPFs repetidos após a normalização. Os campos ``"password"``, ``"name"``
e ``"email"`` também são obrigatórios; campos extras e JSON malformado são
rejeitados.

Quando ``GOVBR_FAKE_USERS_FILE`` está definido, o arquivo substitui por completo
os usuários incluídos: não há mesclagem com os defaults. A página inicial
também deixa de listar credenciais; o usuário informa CPF e senha diretamente
no provedor local. O repositório JSON é carregado em memória e não depende de
ORM, banco ou migrações. Atenção: não use credenciais reais; mantenha o arquivo
fora do Git.

Para integração por código, ``govbr_auth.fake`` exporta
``FakeCredentialAuthenticator``, ``InMemoryFakeUserRepository`` e
``JsonFakeUserRepository``. Passe um autenticador ao argumento
``credential_authenticator`` de ``create_fake_govbr_router`` ou
``create_fake_govbr_app`` para habilitar o formulário de CPF e senha.

Replay e estado
---------------

O store em memória rejeita o reuso de authorization codes dentro da mesma
instância. Instâncias distintas não conseguem rejeitar globalmente o replay sem
estado compartilhado. Essa limitação pertence apenas ao fake local e não
descreve o provedor oficial Gov.br. A biblioteca não cria banco, Redis ou estado
remoto.
