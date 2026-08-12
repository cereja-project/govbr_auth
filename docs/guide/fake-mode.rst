Provedor fake local
===================

O fake é um provedor OAuth/OpenID Connect explícito para desenvolvimento. Seus
símbolos existem somente em ``govbr_auth.fake`` e exigem o extra ``[fake]``.
Ele não é fallback do cliente oficial e não é ativado por configuração.

Use a factory pronta::

    uvicorn examples.example_fastapi:create_development_app --factory

Ela monta ``/fake-govbr/authorize``, ``/fake-govbr/token``,
``/fake-govbr/userinfo`` e ``/fake-govbr/jwk`` no mesmo ASGI de exemplo, mas
mantém a criação do consumidor e seu handler inalterados.

Replay e estado
---------------

O store em memória rejeita o reuso de authorization codes dentro da mesma
instância. Instâncias distintas não conseguem rejeitar globalmente o replay sem
estado compartilhado. Essa limitação pertence apenas ao fake local e não
descreve o provedor oficial Gov.br. A biblioteca não cria banco, Redis ou estado
remoto.
