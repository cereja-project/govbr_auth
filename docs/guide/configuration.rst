Configuração
============

Seleção do provedor
-------------------

``GOVBR_PROVIDER`` aceita somente ``official`` ou ``fake``. O default é
``official``. Use ``GOVBR_PROVIDER=fake`` apenas em desenvolvimento.

O launcher ``python -m govbr_auth.fake`` lê o arquivo ``.env`` apenas do
diretório atual. A precedência é: configuração explícita passada pela aplicação,
variável já exportada no ambiente do processo, valor do ``.env`` e, por fim,
o padrão documentado. O ``.env`` nunca sobrescreve uma variável exportada.

Nomes desconhecidos com o prefixo ``GOVBR_`` são rejeitados para que erros de
digitação não ativem silenciosamente um valor padrão. Variáveis reconhecidas,
mas inativas para o provider selecionado, emitem um warning contendo somente
os nomes; valores e segredos não são incluídos. Endpoints oficiais combinados
com ``GOVBR_PROVIDER=fake`` permanecem um erro de configuração.

Provedor oficial
----------------

.. code-block:: text

    GOVBR_PROVIDER=official
    GOVBR_ENVIRONMENT=production
    GOVBR_AUTHORIZATION_URL=https://sso.acesso.gov.br/authorize
    GOVBR_TOKEN_URL=https://sso.acesso.gov.br/token
    GOVBR_USERINFO_URL=https://sso.acesso.gov.br/userinfo/
    GOVBR_CLIENT_ID=seu-client-id
    GOVBR_CLIENT_SECRET=seu-client-secret
    GOVBR_REDIRECT_URI=https://app.example/auth/govbr/callback
    GOVBR_TRANSACTION_SECRET=substitua-pelo-valor-gerado
    GOVBR_ISSUER=https://sso.acesso.gov.br/
    GOVBR_JWKS_URL=https://sso.acesso.gov.br/jwk

``GOVBR_ENVIRONMENT`` identifica o ambiente do provedor Gov.br, não o ambiente
em que a aplicação consumidora está sendo executada. Quando os hosts oficiais
são usados, ``GOVBR_AUTHORIZATION_URL``, ``GOVBR_TOKEN_URL``,
``GOVBR_USERINFO_URL``, ``GOVBR_ISSUER`` e ``GOVBR_JWKS_URL`` devem pertencer
ao mesmo ambiente e corresponder a ``production`` ou ``staging``. Uma mistura
é rejeitada durante a inicialização, antes da criação de clientes HTTP e rotas.
Falhas ao carregar variáveis de ambiente são apresentadas em português, com os
nomes das variáveis que precisam de correção e sem os valores configurados ou
detalhes internos do Pydantic.

``GOVBR_REDIRECT_URI`` não participa dessa comparação porque pertence à
aplicação consumidora. Ela pode usar outro host, mas todas as URLs exigem HTTPS
fora de ``localhost``, ``127.0.0.1`` e ``::1``. Portanto, um DNS de
desenvolvimento acessível pelo Gov.br também precisa servir HTTPS.

HTTPS local com DNS
~~~~~~~~~~~~~~~~~~~

A biblioteca não emite certificados nem inicia um proxy TLS. Mantenha a
aplicação em HTTP no loopback e termine o HTTPS em um proxy reverso:

.. code-block:: text

    https://app.dev.example:443 -> http://127.0.0.1:8000

Uma configuração mínima do Caddy para essa topologia é:

.. code-block:: text

    app.dev.example {
        tls internal
        reverse_proxy 127.0.0.1:8000
    }

Nesse exemplo local, a CA interna do Caddy precisa ser instalada como confiável
no navegador ou dispositivo que receberá o redirecionamento. Para um DNS
público, substitua o hostname reservado pelo domínio real e use um certificado
público válido em vez de ``tls internal``.

Como alternativa, servidores ASGI como o Uvicorn podem receber diretamente o
certificado e a chave TLS. Em todos os casos, esquema, host, porta e caminho de
``GOVBR_REDIRECT_URI`` devem corresponder exatamente à URI cadastrada no
Gov.br. Certificados, chaves privadas e arquivos locais não devem ser
versionados.

Para o ambiente de staging oficial, use o conjunto coerente abaixo:

.. code-block:: text

    GOVBR_ENVIRONMENT=staging
    GOVBR_AUTHORIZATION_URL=https://sso.staging.acesso.gov.br/authorize
    GOVBR_TOKEN_URL=https://sso.staging.acesso.gov.br/token
    GOVBR_USERINFO_URL=https://sso.staging.acesso.gov.br/userinfo/
    GOVBR_ISSUER=https://sso.staging.acesso.gov.br/
    GOVBR_JWKS_URL=https://sso.staging.acesso.gov.br/jwk

``GOVBR_TRANSACTION_SECRET`` protege ``state``, nonce e PKCE. Gere uma vez:

.. code-block:: python

    from govbr_auth import generate_transaction_secret

    print(generate_transaction_secret())

Mantenha o valor secreto e use o mesmo valor em todas as instâncias. Não gere
uma chave nova a cada inicialização.

O backend suporta múltiplos workers sem armazenamento compartilhado porque o
``state`` contém um envelope de transação cifrado e autenticado por Fernet.
Todos os workers precisam da mesma secret ``GOVBR_TRANSACTION_SECRET``. O
envelope tem TTL e preserva os vínculos de PKCE e nonce até o callback.

O ``state`` não é um registro de uso único e pode ser decodificado novamente
durante o TTL. A prevenção de replay é responsabilidade do authorization code
de uso único: o provedor deve invalidá-lo de forma atômica após a primeira
troca. Rotacionar a secret invalida os fluxos que ainda estiverem em andamento.

FakeGov
-------

``GOVBR_FAKE_END_TO_END`` aceita apenas ``true`` ou ``false``. Host, porta,
prefixo e fonte de usuários podem ser alterados por ``GOVBR_FAKE_HOST``,
``GOVBR_FAKE_PORT``, ``GOVBR_FAKE_PROVIDER_PREFIX`` e
``GOVBR_FAKE_USERS_FILE``. O host precisa ser ``localhost``, ``127.0.0.1`` ou
``::1``.

Configuração explícita
----------------------

Aplicações avançadas podem construir ``GovBrRuntimeSettings`` e passá-lo a
``GovBrAuth``. O caminho comum deve preferir variáveis de ambiente e a fachada
do adapter escolhido, mantendo a composição em um único lugar.
