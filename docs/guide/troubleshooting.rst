Solução de problemas
====================

Conexão recusada em ``http://localhost:8000``
---------------------------------------------

O processo da demo não está em execução ou foi iniciado em outro terminal.
Instale o extra e execute novamente::

    pip install "govbr-auth[demo]"
    python -m govbr_auth.demo

Porta 8000 ocupada
------------------

A demo usa a porta 8000 no loopback. Encerre ou reconfigure o processo local
que já a utiliza e execute ``python -m govbr_auth.demo`` novamente. Não exponha
a demo em uma interface de rede para contornar o conflito.

Transação expirada
------------------

Uma transação de autenticação expira por projeto. Volte para a página inicial,
clique em **Entrar com Gov.br** e conclua a nova transação; não reutilize a URL
de callback anterior.

Estado inválido após reiniciar
------------------------------

Reiniciar a aplicação remove as transações mantidas em memória. Inicie um novo
fluxo de login depois do reinício. Não desative a validação de ``state`` para
aceitar callbacks antigos.

Arquivo de usuários ausente ou inválido
---------------------------------------

Se a inicialização falhar com ``fake user JSON file is unavailable``, confira
se ``GOVBR_FAKE_USERS_FILE`` aponta para um arquivo existente e legível. Se a
mensagem for ``fake user JSON is invalid``, valide a sintaxe e o schema descrito
em :doc:`fake-mode`. Uma lista vazia gera ``users must contain at least one
item``; CPFs duplicados também impedem a inicialização.

Corrija o arquivo e reinicie a demo. Não use credenciais reais; mantenha o
arquivo fora do Git.

CPF ou senha inválidos
----------------------

O formulário retorna ``CPF ou senha inválidos.`` com status 401 tanto para um
CPF desconhecido quanto para uma senha incorreta. Confirme os dados no arquivo
configurado, sem registrar ou exibir a senha para diagnóstico. O CPF aceita 11
dígitos com ou sem pontos e hífen.

Configuração oficial e fake misturadas por acidente
---------------------------------------------------

Mantenha a configuração do fake em um bootstrap de desenvolvimento explícito e
as URLs, credenciais e o ``GovBrSettings`` do provedor oficial em uma
configuração separada. Não combine endpoints fake com credenciais oficiais, nem
reduza validações de token, ``state``, nonce, issuer ou TLS para fazer a mistura
funcionar.
