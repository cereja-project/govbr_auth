Teste local em dois comandos
=============================

Instalação
----------

Instale a demonstração empacotada::

    pip install "govbr-auth[demo]"

Execução
--------

Inicie a demonstração local::

    python -m govbr_auth.demo

Abra ``http://localhost:8000``. A demonstração escuta somente no loopback e não
usa credenciais Gov.br.

Fluxo guiado
------------

1. Clique em **Entrar com Gov.br**.
2. Entre com um usuário fictício na tela do provedor local.
3. Acompanhe o retorno para o callback: a página mostra o usuário e as claims
   validadas, sem expor tokens brutos.

Usuários próprios
-----------------

Para substituir os usuários incluídos, defina ``GOVBR_FAKE_USERS_FILE`` com o
caminho de um arquivo JSON antes de iniciar a demo. O objeto usa a lista
``"users"`` e cada item contém ``"cpf"``, ``"password"``, ``"name"`` e
``"email"``. Consulte :doc:`fake-mode` para copiar o formato completo.

A demo valida o arquivo na inicialização, substitui todos os defaults e não
lista as credenciais externas na página inicial. A fonte funciona em memória,
sem ORM ou banco. Atenção: não use credenciais reais; mantenha o arquivo fora
do Git.

O que usar depois da demonstração
---------------------------------

Para integrar a sua aplicação com o Gov.br, siga a :doc:`configuration` e
execute o seu consumidor FastAPI. Para testar essa integração sem credenciais
oficiais, monte explicitamente o provedor de desenvolvimento em
:doc:`fake-mode`; ele não é ativado por uma flag nem por detecção de URL.

O projeto é comunitário e não é mantido, homologado nem endossado pelo Governo
Federal.
