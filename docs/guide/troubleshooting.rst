Solução de problemas
====================

Instalação ou launcher ausente
------------------------------

Instale o extra que contém dependências do servidor local::

    pip install "govbr-auth[fake]"
    python -m govbr_auth.fake

Porta ocupada
-------------

O launcher usa a porta 8000. Encerre o processo local que já a utiliza ou
defina ``GOVBR_FAKE_PORT`` com outra porta válida. Não exponha o FakeGov em uma
interface de rede.

Provider ou booleano inválido
-----------------------------

``GOVBR_PROVIDER`` aceita apenas ``official`` e ``fake``.
``GOVBR_FAKE_END_TO_END`` aceita exatamente ``true`` ou ``false`` em
minúsculas. Corrija a variável e reinicie o processo.

Host recusado
-------------

``GOVBR_FAKE_HOST`` aceita somente ``localhost``, ``127.0.0.1`` ou ``::1``.
Essa restrição evita publicar acidentalmente o simulador na rede.

Arquivo de usuários ausente ou inválido
---------------------------------------

Se ``GOVBR_FAKE_USERS_FILE`` não existir ou não puder ser lido, a inicialização
falha. O JSON deve conter ``{"users": [...]}``; cada item exige ``"cpf"``,
``"password"``, ``"name"`` e ``"email"``. Não use credenciais reais.

Transação expirada ou estado inválido
-------------------------------------

Volte ao início e crie um novo fluxo. Não desative validação de ``state``,
nonce ou PKCE.

O ``state`` é um envelope Fernet com TTL, PKCE e nonce; ele não depende do
processo que iniciou o login. Em múltiplos workers sem armazenamento
compartilhado, confirme que todos receberam a mesma secret
``GOVBR_TRANSACTION_SECRET`` e que ela não foi rotacionada durante o fluxo.

O ``state`` não é um registro de uso único. Se o mesmo callback for repetido
dentro do TTL, a rejeição segura deve vir do authorization code de uso único
que o provedor invalida na primeira troca.

Configuração oficial conflitante com FakeGov
---------------------------------------------

Ao usar ``GOVBR_PROVIDER=fake``, remova variáveis de endpoints oficiais. A
biblioteca rejeita a mistura para evitar um grafo ambíguo.
