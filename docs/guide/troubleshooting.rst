Solução de problemas
====================

Conexão recusada em ``http://localhost:8000``
---------------------------------------------

O processo da demo não está em execução ou foi iniciado em outro terminal.
Instale o extra e execute novamente::

    python -m pip install "govbr-auth[demo]"
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

Configuração oficial e fake misturadas por acidente
---------------------------------------------------

Mantenha a configuração do fake em um bootstrap de desenvolvimento explícito e
as URLs, credenciais e o ``GovBrSettings`` do provedor oficial em uma
configuração separada. Não combine endpoints fake com credenciais oficiais, nem
reduza validações de token, ``state``, nonce, issuer ou TLS para fazer a mistura
funcionar.
