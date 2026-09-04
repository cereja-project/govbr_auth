Fluxo completo de comunicação
=============================

O ``govbr-auth`` atua no backend da aplicação. O frontend chama a API, e a
API coordena o fluxo OAuth/OIDC.

Visão geral
-----------

O mesmo adapter pode usar Gov.br oficial ou FakeGov; somente o runtime muda.
O FakeGov é um simulador do provedor, não o frontend da aplicação.

.. image:: ../media/provider-switch.svg
   :alt: Frontend e API permanecem iguais enquanto GOVBR_PROVIDER seleciona o Gov.br oficial ou o FakeGov.
   :align: center

Fluxo recomendado
-----------------

``GOVBR_REDIRECT_URI`` aponta para o callback da API::

    GOVBR_REDIRECT_URI=https://api-dev.example.com/auth/govbr/callback

O frontend inicia ``/auth/govbr/login``. Depois da autorização, o navegador
retorna ao callback; o backend mantém ``state``, nonce e PKCE, troca o código,
valida o ID Token e consulta ``userinfo``.

Use HTTPS em toda comunicação com o provedor oficial. Em mobile, o fluxo deve
abrir no navegador nativo, sem WebView. A página que recebe o ``code`` deve
redirecionar após o callback, e a aplicação deve criar sua própria sessão.
Armazene tokens no backend; o access token é usado para APIs autorizadas e o
ID token é usado para identificação, sem ser enviado a APIs. O logout deve ser
iniciado pelo frontend pela rota configurada e retornar ao destino previamente
autorizado.

.. image:: ../media/authentication-sequence.svg
   :alt: Sequência entre navegador, API com govbr-auth e provedor OAuth OIDC.
   :align: center

Provedor oficial
----------------

Com ``GOVBR_PROVIDER=official``, as chamadas vão aos endpoints oficiais
configurados. O core valida assinatura, algoritmo, issuer, audience, claims
temporais, ``state``, PKCE e nonce.

FakeGov na API
--------------

Com ``GOVBR_PROVIDER=fake``, as rotas FakeGov são montadas na mesma API e as
chamadas internas usam ``FakeGovHttpTransport``. O código consumidor permanece
igual. Para uma página visual de demonstração, use o launcher
``python -m govbr_auth.fake``; em modo fake, os adapters também a montam na
raiz ``/``.

FakeGov compartilhado
---------------------

O launcher local usa loopback. Um ambiente compartilhado exigiria origem
pública explícita, TLS, isolamento de dados de teste e controles
administrativos; não é oferecido por esta versão.
