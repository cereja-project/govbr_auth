# Diretrizes do repositório

## Idioma das instruções

Escreva instruções, análises, revisões e documentação de processo em português
do Brasil. Preserve identificadores de código, caminhos, comandos, nomes de
protocolos e texto citado no idioma original.

## Estrutura e versões suportadas

Este é um pacote Python assíncrono compatível com Python 3.11 a 3.14. A
composição compartilhada e os contratos de protocolo ficam em
`govbr_auth/core/`; a composição em tempo de execução fica em
`govbr_auth/runtime.py`; o provedor local FakeGov fica em `govbr_auth/fake/`.
Os adaptadores públicos devem permanecer idiomáticos para FastAPI, Django e
Flask.

Mantenha exemplos executáveis em `examples/`, fontes Sphinx em `docs/` e testes
organizados por finalidade em `tests/unit/`, `tests/integration/`,
`tests/contract/` e `tests/test_django_auth/`.

## Limites arquiteturais

- `govbr_auth/core/` e `govbr_auth/runtime.py` são neutros de framework e não
  podem importar FastAPI, Starlette, Django, Flask ou Werkzeug.
- Adaptadores não devem recriar composição, armazenamento, validação de tokens
  ou regras de domínio já pertencentes ao núcleo.
- Preserve uma superfície pública pequena, tipada e idiomática. Mudanças
  incompatíveis exigem autorização explícita e estratégia de migração.
- Prefira composição local e limites existentes. Não introduza fábricas,
  encapsuladores ou abstrações genéricas sem repetição concreta e consumidor
  real.
- Faça apenas a menor mudança necessária; não inclua limpeza lateral,
  refatoração oportunista ou alternativa silenciosa.

## Invariantes de segurança

- Trate OAuth 2.0 e OpenID Connect como limites de segurança. Preserve PKCE
  exclusivamente com S256, nonce imprevisível e validação do nonce no ID token.
- O `state` transporta uma transação autenticada e criptografada, com emissão e
  expiração validadas. Instâncias distintas devem interoperar usando a mesma
  chave secreta e uma tolerância temporal configurada de forma consistente.
- Não afirme que o próprio `state` é de uso único. A proteção contra
  reutilização maliciosa depende também do código de autorização descartável,
  PKCE e nonce.
- Valide assinatura, algoritmo permitido, `issuer`, `audience`, `kid`,
  declarações temporais e rotação ou falha de JWKS de forma fechada.
- Exija HTTPS fora de loopback, valide redirecionamentos e preserve atributos
  seguros de cookies quando houver mudança nesse limite.
- Erros e logs não podem revelar verificador, nonce, state, código de
  autorização, tokens, chaves, conteúdo descriptografado nem dados pessoais.
- FakeGov é habilitado explicitamente e separado do provedor oficial. A
  proibição de credenciais reais aplica-se ao FakeGov; a integração oficial é
  destinada ao uso real.
- Nunca versione credenciais, tokens, chaves ou dados reais de usuários.

## Ambiente e comandos de desenvolvimento

Use ambiente virtual isolado e não altere o Python global:

```bash
python -m pip install -r requirements-dev.txt
```

Execute a suíte completa:

```bash
python -m pytest --tb=short --disable-warnings -q
```

Configure `--basetemp` e `cache_dir` para diretórios temporários externos ao
repositório. Não crie no projeto `.pytest-*`, `.pytest_cache`, `task*`, saídas
de documentação ou distribuições temporárias.

Formate e execute o lint bloqueante somente nos diretórios versionados:

```bash
python -m black govbr_auth tests examples scripts
python -m flake8 govbr_auth tests examples scripts --count --select=E9,F63,F7,F82 --show-source --statistics
```

Gere wheel e sdist com `python -m build` usando um diretório de saída externo e
valide os artefatos com Twine e `scripts/verify_distribution.py`. Para exercitar
o fluxo local completo, configure `GOVBR_PROVIDER=fake` e
`GOVBR_DEMO_PAGE=true`, então execute `python -m govbr_auth.fake`.

## Código Python

Use quatro espaços, anotações de tipo e APIs assíncronas quando as dependências
forem assíncronas. Use `snake_case` para módulos, funções e variáveis,
`PascalCase` para classes e `UPPER_SNAKE_CASE` para constantes. Mantenha
importações explícitas e estáveis; não manipule `sys.path` para encobrir
problemas de empacotamento.

Use as ferramentas e dependências já configuradas. Não introduza framework,
gerenciador de dependências ou mecanismo criptográfico alternativo sem
necessidade aprovada.

## Testes e evidências

Use pytest com `pytest-asyncio`; arquivos e testes devem seguir `test_*.py` e
`test_*`. Para comportamento novo, alterado ou corrigido, observe o RED antes
da implementação e faça a menor mudança que produza GREEN. Teste comportamento
observável e contratos reais, não apenas chamadas de dublês.

Adicione ou atualize testes para toda mudança de comportamento, especialmente
em autenticação, JWT/JWKS, redirecionamentos, cookies, state, PKCE, nonce, tempo,
concorrência e interoperabilidade entre instâncias. Execute primeiro o teste
focal e depois a regressão proporcional ao risco. Suíte verde e cobertura não
substituem casos discriminantes.

Mantenha `requirements-min.txt` alinhado aos pisos de `pyproject.toml`. Mudanças
de dependências exigem ambiente mínimo isolado, `pip check` e auditoria de
vulnerabilidades. O candidato a lançamento exige cobertura global mínima de
90%, 100% nos ramos críticos definidos pelo projeto e CI multiplataforma verde.

## Documentação, commits e pull requests

Atualize README, documentação Sphinx e `CHANGELOG.md` quando o comportamento
observável mudar. Não apresente o FakeGov como caminho para credenciais reais e
não atribua ao próprio `state` garantia contra reutilização que ele não oferece.

Use assuntos Conventional Commits curtos, como
`fix(runtime): validate prefix` ou `docs(fake): clarify setup`. Mantenha cada
commit e PR focado no problema autorizado. A descrição do PR deve registrar
problema, solução, issue relacionada, comandos realmente executados e impactos
de segurança e compatibilidade.

Não declare uma verificação como concluída sem executar o comando e observar
seu resultado. Não contorne verificações obrigatórias, revisão humana ou
proteção de branch. Não crie tag, GitHub Release nem publicação PyPI sem
autorização explícita.
