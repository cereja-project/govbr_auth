Fluxos de comunicação
=====================

O ``GovBrAuth`` mantém a mesma fachada para o provedor oficial e para o
FakeGov. A configuração escolhe o grafo de runtime; ela não altera o código
da aplicação.

Fluxo com o provedor oficial
----------------------------

Neste modo, o navegador conversa com o Gov.br durante a autorização e o
backend conversa diretamente com os endpoints oficiais para trocar o código,
buscar as chaves públicas e consultar os dados do usuário::

    Navegador             Aplicação FastAPI              Gov.br
        |                         |                        |
        | GET /auth/govbr/login   |                        |
        |------------------------>|                        |
        |<-- redirect authorize - |                        |
        |------------------------------------------------->|
        |<-- login e consentimento ------------------------|
        |------------------------------------------------->|
        |<-- redirect callback?code&state -----------------|
        |                         |                        |
        | GET /auth/govbr/callback|                        |
        |------------------------>|                        |
        |                         | POST /token            |
        |                         |----------------------->|
        |                         |<-- access/id token ----|
        |                         | GET /jwk               |
        |                         |----------------------->|
        |                         |<-- chaves públicas ---|
        |                         | GET /userinfo         |
        |                         |----------------------->|
        |                         |<-- identidade ---------|
        |<-- on_success ----------|                        |

O backend valida ``state``, PKCE, ``nonce``, assinatura, ``issuer``,
``audience`` e o vínculo entre o ``subject`` do ID Token e o ``userinfo``.
Tokens e segredos não são enviados ao navegador pelo fluxo padrão.

Fluxo com FakeGov no aplicativo
-------------------------------

Com ``GOVBR_PROVIDER=fake``, ``GovBrAuth`` inclui as rotas do FakeGov no
mesmo ``APIRouter`` da aplicação. O navegador continua fazendo requisições
HTTP normais, mas as chamadas de backend para ``token``, ``jwk`` e
``userinfo`` usam um transporte ASGI em memória. Não há chamada de rede para
um servidor externo::

    Navegador       Aplicação FastAPI       Rotas FakeGov       Runtime core
        |                   |                    |                  |
        |-- login --------->|                    |                  |
        |<-- redirect ----- |                    |                  |
        |------------------ /fake-govbr/authorize ----------------->|
        |<-- login/redirect |                    |                  |
        |-- callback ------>|                    |                  |
        |                   |-- ASGI POST token ->|                  |
        |                   |<-- token ----------|                  |
        |                   |-- ASGI GET jwk ---->|                  |
        |                   |<-- keys -----------|                  |
        |                   |-- ASGI GET userinfo>|                  |
        |                   |<-- user ------------|                  |
        |<-- on_success --- |                    |                  |

Esse modo é indicado para desenvolvimento e testes de integração. Ele
preserva os limites HTTP e OAuth sem depender da disponibilidade do provedor
oficial.

Fluxo end-to-end do launcher
----------------------------

Com ``GOVBR_FAKE_END_TO_END=true python -m govbr_auth.fake``, o launcher
cria uma aplicação completa com página inicial, fachada do consumidor e
FakeGov. O navegador acessa ``http://localhost:8000``; o backend e o FakeGov
continuam no mesmo processo, usando o mesmo grafo de runtime::

    Navegador
        |
        v
    Página inicial -> /auth/govbr/login -> /fake-govbr/authorize
        ^                                      |
        |                                      v
        +------ resultado <--- callback <--- login FakeGov

Esse launcher é uma ferramenta local de demonstração. Em uma aplicação real,
monte ``GovBrAuth`` e inclua ``auth.router`` explicitamente.

Escolha do modo
---------------

``GOVBR_PROVIDER=official`` (padrão)
    Usa os endpoints oficiais configurados e não monta rotas FakeGov.

``GOVBR_PROVIDER=fake``
    Monta o FakeGov no adaptador FastAPI e usa transporte ASGI em memória.

``GOVBR_FAKE_END_TO_END=true``
    É usado pelo launcher local para publicar também a página inicial. Não é
    necessário no código de uma aplicação que já usa ``GovBrAuth``.
