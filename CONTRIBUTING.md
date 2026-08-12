# Contribuindo com o GovBR Auth

## Antes de começar

Procure nas [issues existentes](https://github.com/cereja-project/govbr_auth/issues) antes de iniciar uma alteração. Para bugs e propostas, use o formulário correspondente ao abrir uma nova issue.

Ao participar do projeto, siga o [Código de Conduta](CODE_OF_CONDUCT.md).

## Preparação do ambiente

O projeto requer Python 3.11 ou mais recente.

```bash
python -m venv .venv
```

Ative o ambiente no Windows:

```powershell
.\.venv\Scripts\Activate.ps1
```

Ou em sistemas POSIX:

```bash
source .venv/bin/activate
```

Instale o pacote e as dependências de desenvolvimento:

```bash
python -m pip install -r requirements-dev.txt
python -m pip install flake8
```

## Desenvolvimento e validação

Use o simulador local durante o desenvolvimento. Nunca use credenciais, tokens, chaves ou dados reais de usuários em testes, exemplos, issues ou pull requests.

```bash
USE_FAKE_GOVBR=true uvicorn examples.example_simple_app:app --reload
```

Execute a suíte de testes:

```bash
python -m pytest --tb=short --disable-warnings -q
```

Formate os arquivos Python antes de enviar a contribuição:

```bash
black govbr_auth tests examples
```

Execute a verificação bloqueante usada pela CI:

```bash
flake8 govbr_auth tests examples --count --select=E9,F63,F7,F82 --show-source --statistics
```

## Branches e commits

Use uma branch curta e focada, com um destes prefixos:

- `fix/` para correções;
- `feat/` para funcionalidades;
- `docs/` para documentação;
- `test/` para testes;
- `chore/` para manutenção.

Os commits seguem [Conventional Commits](https://www.conventionalcommits.org/):

```text
fix(controller): corrige tratamento de callback inválido
docs(fake-mode): esclarece configuração local
test(jwt): cobre token expirado
```

## Issues

Um relato de bug deve conter uma reprodução mínima, versões relevantes e o comportamento esperado e observado. Remova informações sensíveis de logs e tracebacks.

Uma proposta de funcionalidade deve explicar primeiro o problema, depois a solução desejada, as alternativas consideradas e qualquer impacto previsto na API pública.

## Pull requests

Mantenha cada pull request limitado a um problema. Relacione a issue correspondente e explique como a mudança foi validada.

Mudanças de comportamento devem incluir testes. Atualize a documentação e o `CHANGELOG.md` no mesmo pull request quando houver impacto observável para usuários.

Alterações em state, PKCE, JWT, redirects, cookies ou validação de tokens são sensíveis à segurança e devem declarar explicitamente seu impacto.

## Definição de pronto

Uma contribuição está pronta para revisão quando:

- a suíte de testes passa;
- os arquivos Python alterados foram formatados com Black;
- a verificação bloqueante do Flake8 passa;
- testes cobrem mudanças de comportamento, quando aplicável;
- documentação e changelog foram atualizados, quando aplicável;
- não há credenciais, tokens, chaves ou dados reais de usuários;
- impactos de segurança e compatibilidade estão declarados;
- o escopo está limitado ao problema descrito.
