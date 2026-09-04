Solução de problemas
====================

Instalação ou launcher ausente
------------------------------

Instale o extra necessário::

    pip install "govbr-auth[fake]"
    python -m govbr_auth.fake

Porta ocupada
-------------

O launcher usa a porta configurada em ``GOVBR_FAKE_PORT`` e mantém o host em
loopback. Escolha outra porta válida se necessário; não publique o FakeGov na
rede.

Provider ou variável desconhecida
---------------------------------

``GOVBR_PROVIDER`` aceita apenas ``official`` e ``fake``. Nomes desconhecidos
com prefixo ``GOVBR_`` interrompem a inicialização. Confira a grafia e a
versão instalada. Nunca são exibidos valores de configuração ou segredos.

Página de demonstração
----------------------

A página ``/`` é criada somente por ``python -m govbr_auth.fake`` ou
``create_fake_app``; ``/govbr-auth-demo`` é um alias. Ela não é adicionada pelos adapters. Se o launcher não
mostrar a página, confirme que o extra ``fake`` está instalado, que o provedor
fake foi selecionado e que o app usado é o launcher.

Host recusado
-------------

``GOVBR_FAKE_HOST`` aceita somente ``localhost``, ``127.0.0.1`` ou ``::1``.

Arquivo de usuários ausente ou inválido
---------------------------------------

``GOVBR_FAKE_USERS_FILE`` deve apontar para um JSON com ``{"users": [...]}``.
Cada item exige CPF, senha, nome e email fictícios. Não use credenciais reais.

Transação expirada ou estado inválido
-------------------------------------

Volte ao início e crie um novo fluxo. Não desative validação de ``state``,
nonce ou PKCE. O envelope Fernet tem TTL. Em múltiplos workers, use a mesma
``GOVBR_TRANSACTION_SECRET``. O ``state`` não é um registro de uso único; o
authorization code descartável é o limite de replay do provedor.
O state não é um registro de uso único; o authorization code de uso único
limita replay.
