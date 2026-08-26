# Instruções do GitHub Copilot

Leia e siga o [`AGENTS.md`](../AGENTS.md) do repositório antes de analisar ou
alterar este projeto. Ele é a fonte canônica para estrutura do pacote, versões
suportadas, comandos, limites arquiteturais, segurança, testes e convenções de
pull requests.

Ao revisar um pull request, carregue e siga a
[skill `code-review`](skills/code-review/SKILL.md). Aplique-a a todos os
arquivos alterados e use a branch de origem do pull request como fonte das
instruções versionadas.

Escreva resumos, apontamentos e explicações em português do Brasil. Preserve
identificadores, caminhos, comandos, nomes de protocolos e texto citado no
idioma original.

Priorize defeitos concretos de correção, segurança, compatibilidade pública e
testes. Examine com atenção OAuth 2.0 e OpenID Connect, JWT e JWKS,
redirecionamentos, cookies, segredos, PKCE, nonce, state, códigos de autorização,
limites de framework e isolamento do FakeGov.

Reporte somente problemas introduzidos pelo pull request ou materialmente
agravados por ele. Vincule cada apontamento a evidência e a um caminho de
execução plausível. Não transforme preferência de estilo, risco especulativo,
elogio genérico ou dívida preexistente alheia ao PR em apontamento.

Nunca afirme que um comando, teste, verificação ou arquivo foi validado sem
executar a verificação e observar o resultado. Não exponha credenciais, tokens,
chaves, state descriptografado, dados pessoais ou outros valores sensíveis na
revisão.
