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
retorna ao callback; o adapter verifica uma prova de navegador independente
do ``state`` antes de qualquer troca de código. O core valida a transação,
troca o código com PKCE, valida o ID Token e consulta ``userinfo``.

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

No README, a versão animada percorre as doze setas em ordem com um marcador
verde, em um ciclo de 24 segundos. Todos os textos permanecem visíveis.
Quando a preferência por movimento reduzido está ativada no sistema ou
navegador, essa versão também permanece estática.

Provedor oficial
----------------

Com ``GOVBR_PROVIDER=official``, as chamadas vão aos endpoints oficiais
configurados. O core valida assinatura, algoritmo, issuer, audience, claims
temporais, ``state``, PKCE e nonce.

FakeGov na API
--------------

Com ``GOVBR_PROVIDER=fake``, as rotas FakeGov são montadas na mesma API e as
chamadas internas usam ``FakeGovHttpTransport``. O código consumidor permanece
igual. Os adapters podem montar a página inicial de demonstração na raiz ``/``,
mas mantêm o callback sob controle do ``on_success`` da aplicação. Para a
experiência visual completa, use o launcher ``python -m govbr_auth.fake``: ele
abre a autenticação em uma nova guia ou janela nativa e atualiza a página
original depois da validação do callback.

FakeGov compartilhado
---------------------

O launcher local usa loopback. Um ambiente compartilhado exigiria origem
pública explícita, TLS, isolamento de dados de teste e controles
administrativos; não é oferecido por esta versão.

Vínculo com o navegador
----------------------

As rotas de login dos três adapters e ``create_govbr_router`` emitem um cookie
``HttpOnly`` autenticado com Fernet. A prova vincula o resumo do ``state`` ao
cliente e à URI de callback, com validade de cinco minutos. Ela não é enviada
ao provedor e não inclui código de autorização, tokens, verificador PKCE, nonce
ou dados pessoais. Ter somente um ``state`` válido não permite criar a prova.

O callback exige essa prova antes de chamar o provedor ou aceitar um erro OAuth.
A ausência, adulteração ou associação a outra transação resulta em
``invalid_state``; a expiração resulta em ``expired_transaction``. As respostas
normais do callback, incluindo erros e hooks personalizados, removem somente
o cookie da transação concluída e usam ``Cache-Control: no-store`` e
``Pragma: no-cache``. Cookies de sessão da aplicação são preservados.

Em HTTPS, são usados prefixo ``__Host-``, ``Secure``, ``Path=/``, nenhum
``Domain`` e ``SameSite=None``. Isso permite os callbacks POST já suportados em
Django e Flask. A exceção HTTP é restrita ao loopback validado na configuração,
com nome distinto e ``SameSite=Lax``. Não se deduz a política de cookies de
``Forwarded`` ou ``X-Forwarded-Proto``.

Use navegação pelo navegador para iniciar a rota de login, no mesmo host do
callback. Fluxos server-to-server que retornam apenas a URL de autorização,
transferência de callback entre navegadores e callbacks anteriores à atualização
não possuem a prova e precisam reiniciar o login. Múltiplas abas são suportadas
por cookies separados, limitados a oito tentativas pendentes por cliente e URI
de callback; abrir mais tentativas pode invalidar uma anterior.

O envelope OAuth do core permanece inalterado. Consumidores que usam diretamente
``GovBrClient`` devem prover sua própria vinculação ao navegador antes de chamar
``exchange_code``. O cookie do adapter não substitui a sessão autenticada da
aplicação nem transforma o ``state`` em um registro de uso único no servidor.

Ciclo de vida em WSGI
--------------------

Django e Flask executam as operações assíncronas em um loop dedicado, criado
sob demanda por processo. As autenticações consecutivas e concorrentes usam o
mesmo loop, inclusive para fechar clientes HTTP de propriedade do adapter.
O contexto de cada chamada é preservado sem compartilhar variáveis de contexto
entre requisições.

Prefira fornecer ``settings`` ao adapter e chamar ``auth.close()`` no
encerramento do worker. Um runtime fornecido pela aplicação é emprestado: o
adapter não o fecha. Para encerrar um runtime usado por WSGI no mesmo loop,
use ``govbr_auth.adapters._sync.run_sync(runtime.aclose)``; não use
``asyncio.run(runtime.aclose())`` em um loop diferente.

Crie e utilize os recursos HTTP depois do fork do worker. Não compartilhe um
runtime HTTP já utilizado com outro processo ou loop ASGI independente. O loop
WSGI não altera o ciclo de vida nativo do adapter FastAPI.
