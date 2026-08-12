Quick start FastAPI
===================

Instalação
----------

Instale o cliente e o adaptador FastAPI::

    pip install govbr-auth

Para executar também o provedor local explícito::

    pip install "govbr-auth[fake]"

Exemplo executável
------------------

Defina as variáveis descritas em :doc:`configuration` e inicie o consumidor::

    uvicorn examples.example_fastapi:create_app --factory

A factory cria ``GovBrSettings``, ``GovBrClient`` e ``GovBrAuth``. O endpoint
``/auth/govbr/login`` inicia o fluxo e ``/auth/govbr/callback`` entrega ao
handler apenas usuário e claims validados. Tokens brutos continuam ocultos por
padrão.

Desenvolvimento local
---------------------

O fake não é ativado por flag nem por detecção de URL. Configure os endpoints
de loopback e execute explicitamente::

    uvicorn examples.example_fastapi:create_development_app --factory

Essa factory preserva o mesmo consumidor e handler, monta separadamente as
rotas do provedor fake e muda somente a configuração dos endpoints e
credenciais.
