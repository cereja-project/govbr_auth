Fluxo completo de comunicação
=============================

O ``govbr-auth`` atua no backend da aplicação. O frontend da aplicação não
fala diretamente com o Gov.br nem com o FakeGov: ele chama a API, e a API
coordena todo o fluxo OAuth/OIDC.

Visão geral
-----------

O mesmo backend pode usar o Gov.br oficial ou o FakeGov. A troca de provedor
ocorre na composição do runtime, sem alterar o código do frontend ou da API::

    Frontend da aplicação
             |
             | chamadas HTTP da aplicação
             v
    API FastAPI + govbr-auth
             |
             | OAuth/OIDC: authorize, token, jwk, userinfo
             v
    Provedor: Gov.br oficial OU FakeGov

O FakeGov é um simulador do provedor. Ele não é o frontend da aplicação. A
interface HTML de login que ele oferece existe somente para representar a tela
que normalmente seria apresentada pelo provedor durante o redirect OAuth.

Fluxo recomendado: callback na API
----------------------------------

O ``GOVBR_REDIRECT_URI`` deve apontar para a API, por exemplo::

    GOVBR_REDIRECT_URI=https://api-dev.example.com/auth/govbr/callback

O frontend inicia o login pela API. Depois que o provedor conclui a
autorização, o navegador volta para o callback da API. Assim, o backend pode
manter o ``state``, o nonce, o PKCE e a troca de tokens sob seu controle::

    Frontend       API + govbr-auth       Gov.br ou FakeGov
        |                  |                       |
        | GET /auth/govbr/login                      |
        |----------------->|                       |
        |                  | gera state, nonce, PKCE
        |                  |                       |
        |<-- redirect para /authorize --------------|
        |----------------------------------------->|
        |                  |                       |
        |<-- tela de login/consentimento ---------|
        |----------------------------------------->|
        |                  |                       |
        |<-- redirect para API /callback?code&state|
        |----------------->|                       |
        |                  |                       |
        |                  | POST /token ---------->
        |                  |<-- access/id token ---|
        |                  |                       |
        |                  | GET /jwk ------------>
        |                  |<-- chaves públicas ---|
        |                  |                       |
        |                  | valida assinatura,     |
        |                  | issuer, audience,      |
        |                  | nonce e subject       |
        |                  |                       |
        |                  | GET /userinfo ------->|
        |                  |<-- identidade --------|
        |                  |                       |
        |<-- sessão/resultado autenticado ---------|

O navegador nunca precisa receber o client secret, o access token ou o ID
Token para que a API conclua a autenticação.

Provedor oficial
----------------

Com ``GOVBR_PROVIDER=official``:

* a API redireciona o navegador para os endpoints oficiais;
* a API troca o authorization code diretamente com o Gov.br;
* a API busca o JWKS e consulta ``userinfo``;
* o core valida ``state``, PKCE, nonce, assinatura, issuer, audience e subject.

FakeGov embutido na API
-----------------------

Com ``GOVBR_PROVIDER=fake``, as rotas do FakeGov são montadas na mesma API
FastAPI. Não é necessário iniciar outro processo. O frontend continua chamando
a API, e o navegador acessa as rotas FakeGov durante o redirect. As chamadas
internas da API para ``token``, ``jwk`` e ``userinfo`` usam transporte ASGI em
memória::

    Frontend       API FastAPI             FakeGov montado       Core
        |                |                       |                 |
        |-- /login ----->|                       |                 |
        |<-- redirect ---|                       |                 |
        |---------------- /fake-govbr/authorize ----------------->|
        |<-- tela de login FakeGov --------------|                 |
        |---------------- /callback?code&state -->|                 |
        |                |                       |                 |
        |                |-- ASGI POST /token --->|                 |
        |                |<-- tokens -------------|                 |
        |                |-- ASGI GET /jwk ------>|                 |
        |                |<-- chaves -------------|                 |
        |                |-- ASGI GET /userinfo ->|                 |
        |                |<-- usuário ------------|                 |
        |                |------------------------------------------>| valida
        |<-- resultado --|                       |                 |

O FakeGov simula as respostas do provedor; as regras de segurança continuam
sendo responsabilidade do core e do fluxo da API.

Launcher end-to-end
-------------------

O comando abaixo adiciona uma página inicial de demonstração para tornar o
primeiro teste manual imediato::

    GOVBR_FAKE_END_TO_END=true python -m govbr_auth.fake

Essa página inicial é um frontend temporário de demonstração. Em uma
aplicação real, ela é substituída pelo frontend da aplicação, que chama a API.
A API e o FakeGov continuam no mesmo processo.

FakeGov compartilhado
---------------------

O mesmo modelo pode ser publicado em uma API acessível aos desenvolvedores e
testadores. Nesse caso, a API expõe suas rotas FakeGov e o frontend usa a URL
pública da API. A configuração precisa distinguir a origem pública usada pelo
navegador do transporte interno usado pela API.

A implementação atual usa loopback como padrão de segurança para o launcher
local. Um modo compartilhado exige uma configuração explícita de origem
pública, além de isolamento de usuários e tokens de teste, rotação de chaves,
TLS e controles administrativos.

Escolha do modo
---------------

``GOVBR_PROVIDER=official`` (padrão)
    Usa os endpoints oficiais configurados.

``GOVBR_PROVIDER=fake``
    Monta o FakeGov na mesma API e usa transporte ASGI interno para as chamadas
    do backend.

``GOVBR_FAKE_END_TO_END=true``
    Ativa a página inicial de demonstração do launcher. Não é necessário em
    uma aplicação que já possui seu próprio frontend.
