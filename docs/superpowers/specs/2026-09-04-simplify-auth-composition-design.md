# Simplificação da composição de autenticação

## Contexto

As alterações recentes introduziram `GovBrApplicationSettings`, a opção
`demo_page` nos três adapters e um segundo caminho de composição no launcher
FakeGov. O resultado tornou o caminho documentado mais longo e espalhou a
mesma responsabilidade entre FastAPI, Django, Flask e o launcher.

O objetivo desta mudança é fechar a v1 com uma composição única e explícita:
o núcleo monta runtime e serviço de autenticação; cada adapter injeta somente
o registro de rotas e a conversão de request/response exigidos pelo seu
framework.

## Decisão

Será removida a camada de aplicação que mistura configuração de runtime com
apresentação. `GovBrApplicationSettings` e `demo_page` não farão parte da API
de `GovBrAuth` nem da configuração compartilhada do runtime.

Os adapters continuarão expondo `GovBrAuth` em seus próprios módulos. Esses
nomes iguais são pontos de entrada idiomáticos para frameworks diferentes; não
conterão mais composição OAuth, seleção de provider, criação de serviço ou
regras de erro duplicadas.

A página demo será responsabilidade exclusiva da composição FakeGov
end-to-end. Ela não será injetada em aplicações oficiais ou em adapters
genéricos. A aplicação consumidora terá apenas as rotas de login e callback;
o launcher FakeGov poderá adicionar sua própria página local quando o perfil
end-to-end for selecionado.

## Arquitetura proposta

### Núcleo compartilhado dos adapters

Criar um componente interno, sem imports de FastAPI, Django, Flask ou
Werkzeug, que contenha:

- `RuntimeOwner` e o runtime resolvido;
- uma única instância de `AuthenticationService`;
- prefixo, caminho de login, caminho de callback e clock resolvidos;
- operações assíncronas para gerar a autorização e autenticar o callback.

Uma factory interna será responsável por chamar `create_adapter_runtime`,
validar a topologia antes da alocação e construir esse componente. A factory
continuará recebendo a função de transporte FakeGov como dependência injetada;
o runtime neutro não importará frameworks web.

### Adapters

Cada adapter público fará somente quatro coisas:

1. receber o callback tipado do framework;
2. obter o núcleo compartilhado;
3. registrar login/callback usando a API nativa do framework;
4. traduzir redirects, respostas de sucesso e erros para o framework.

FastAPI continuará assíncrono. Django e Flask continuarão síncronos e usarão
o executor já existente para chamar o núcleo assíncrono. O tratamento público
de erros permanecerá centralizado em `adapters/_errors.py`.

O uso principal será reduzido para:

```python
from govbr_auth.fastapi import GovBrAuth

auth = GovBrAuth(on_success=authenticated)
app.include_router(auth.router)
```

Quando a aplicação fornecer configuração própria, poderá passar
`GovBrRuntimeSettings` explicitamente. O runtime selecionado continuará sendo
o mesmo para provider oficial e FakeGov; somente os endpoints e o transporte
serão injetados.

### FakeGov e demo

`create_fake_gov_simulator` continuará sendo a única composição do grafo
FakeGov. `create_govbr_runtime` continuará criando o cliente consumidor para
o provider fake por meio de `FakeGovHttpTransport` recebido como factory.

`create_end_to_end_app` não passará mais `demo_page` para `GovBrAuth`. Se o
perfil end-to-end for usado, o próprio launcher registrará explicitamente a
rota `/govbr-auth-demo` e as páginas locais. O adapter consumirá somente login,
callback e, quando aplicável, as rotas do provider fake.

As factories avançadas `create_fake_govbr_router` e
`create_fake_govbr_app` permanecem voltadas ao provider isolado. Não haverá
uma segunda implementação do fluxo OAuth consumidor nessas factories.

### Configuração pública

`GovBrRuntimeSettings` será a única configuração compartilhada entre runtime,
adapters e FakeGov. `from_environment()` continuará validando provider,
endpoints, segredos, prefixos e valores FakeGov. A variável
`GOVBR_DEMO_PAGE` será removida completamente. A seleção de modo será feita
pela factory usada: `create_fake_app` compõe o app end-to-end com a página
local; `create_fake_govbr_app` compõe somente o provider.

## Limites e compatibilidade

Esta é uma mudança incompatível autorizada para a v1. Serão removidos:

- `GovBrApplicationSettings`;
- o argumento `demo_page` dos três `GovBrAuth`;
- a variável `GOVBR_DEMO_PAGE`;
- a injeção de `/govbr-auth-demo` pelos adapters;
- a documentação que apresenta a página demo como parte do adapter oficial.

Serão preservados:

- `GovBrRuntimeSettings`, `GovBrRuntime` e `create_govbr_runtime`;
- os nomes `GovBrAuth` nos módulos `fastapi`, `django` e `flask`;
- `AuthenticationService` e os contratos OAuth/OIDC, PKCE S256, nonce,
  state, JWT/JWKS, HTTPS, cookies e erros seguros;
- `FakeGovSimulator`, as cinco rotas do provider e as factories avançadas;
- a separação de imports entre núcleo, runtime, adapters e frameworks.

Não será criado um adapter base genérico público, um `install(app)` universal
ou uma camada de configuração que apenas agregue flags de apresentação.

## Testes e critérios de aceite

Antes da implementação, os testes novos ou alterados deverão expressar:

- um único núcleo interno compartilhado pelos três adapters;
- construção por ambiente e por `GovBrRuntimeSettings` explícito;
- ausência de imports de frameworks em runtime/core e no novo componente
  compartilhado;
- login, callback válido, callback inválido e mapeamento de erro nos três
  frameworks;
- lifecycle correto para runtime criado e runtime emprestado;
- fluxo FakeGov end-to-end e provider-only sem composição duplicada;
- quickstarts do README e da documentação executáveis em diretório vazio;
- ausência de `GovBrApplicationSettings`, `demo_page` e `GOVBR_DEMO_PAGE` nos
  adapters, runtime e configuração pública;
- build de wheel/sdist contendo somente artefatos publicáveis.

Critérios de fechamento:

```text
python -m pytest --tb=short --disable-warnings -q
python -m black --check govbr_auth tests examples scripts
python -m flake8 govbr_auth tests examples scripts --count --select=E9,F63,F7,F82 --show-source --statistics
python -m build --no-isolation --outdir C:\Users\leite\AppData\Local\Temp\govbr_auth_dist
```

O ambiente de desenvolvimento deverá ter as dependências de build instaladas,
incluindo `setuptools>=84.0.0`; a falha observada na linha de base é de
provisionamento, não será mascarada por alteração no teste.

## Fora de escopo

- alterar o protocolo OAuth/OIDC ou as garantias criptográficas;
- adicionar suporte a outro framework;
- criar um FakeGov remoto ou permitir host não-loopback;
- publicar PyPI, criar tag, release ou fazer push;
- refatorar módulos do provider que não participem da composição duplicada.
