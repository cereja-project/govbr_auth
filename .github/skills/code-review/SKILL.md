---
name: code-review
description: >-
  Use esta skill quando o GitHub Copilot revisar um pull request ou código
  alterado no repositório govbr_auth.
license: MIT
---

# Revisão de pull requests

## Objetivo

Revise mudanças como um revisor somente leitura, orientado por evidências e
limitado ao conteúdo disponível na branch do pull request. Procure defeitos
introduzidos ou agravados pela mudança; não edite arquivos, aprove o PR nem
afirme que sua revisão bloqueia o merge.

Escreva comentários, resumos e explicações em português do Brasil. Preserve
identificadores, caminhos, comandos, nomes de protocolos e texto citado no
idioma original.

## Processo obrigatório

1. Leia a descrição do PR, a branch base, a branch de origem, a lista completa
   de arquivos alterados e o diff integral.
2. Leia o `AGENTS.md`, `.github/copilot-instructions.md` e qualquer arquivo
   `.github/instructions/*.instructions.md` aplicável aos caminhos alterados.
3. Para cada arquivo alterado, examine implementação adjacente, chamadores,
   contratos públicos, testes e documentação necessários para julgar a
   mudança.
4. Identifique quais contratos observáveis foram alterados: API Python, HTTP,
   OAuth/OIDC, configuração, distribuição, documentação ou CI.
5. Execute apenas verificações seguras e focadas que produzam evidência útil.
   Registre o comando e o resultado observado; declare explicitamente o que
   não pôde ser executado.
6. Emita somente apontamentos acionáveis vinculados ao escopo alterado. Una
   ocorrências com a mesma causa raiz em um único apontamento.
7. Confirme no resumo se todos os arquivos alterados foram examinados. Liste
   cada exclusão e seu motivo quando a cobertura for parcial.

Não use recursos pessoais ou locais à máquina, arquivos externos à cópia de trabalho,
prompts privados ou informações que não estejam disponíveis ao Copilot na
branch do PR.

## Prioridades

Analise nesta ordem:

| Prioridade | Procurar por |
| --- | --- |
| 1 | Falhas funcionais, contratos incorretos, corrupção ou perda de dados |
| 2 | Vulnerabilidades, autorização incorreta e exposição de dados sensíveis |
| 3 | Regressões de API pública, protocolo, compatibilidade ou integração |
| 4 | Concorrência, idempotência, tempo, estado e falhas parciais |
| 5 | Testes ausentes ou incapazes de detectar a regressão alterada |
| 6 | Manutenção que dificulte verificar com segurança o comportamento novo |

## Limites críticos do govbr_auth

### OAuth 2.0 e OpenID Connect

- Verifique integridade, confidencialidade, emissão e expiração de `state`.
- Preserve PKCE exclusivamente com S256, nonce imprevisível e validação do
  nonce no ID token.
- Não presuma que o próprio `state` é de uso único. Aponte replay somente com
  base no fluxo completo, incluindo authorization code descartável e PKCE.
- Verifique `issuer`, `audience`, assinatura, algoritmo permitido, `kid`,
  claims temporais e falhas de obtenção ou rotação de JWKS.
- Confirme que erros públicos e logs não revelam verifier, nonce, state,
  authorization code, tokens nem payload descriptografado.

### HTTP, redirects e cookies

- Verifique validação de URLs, HTTPS fora de loopback, prevenção de open
  redirect e preservação da semântica de métodos, status, cabeçalhos e cache.
- Para cookies alterados, confira `Secure`, `HttpOnly`, `SameSite`, escopo,
  expiração e ausência de material sensível indevido.
- Confirme que exceções internas não atravessam o limite HTTP nem mudam o
  contrato público acidentalmente.

### Criptografia, segredos e FakeGov

- Exija falha fechada para chave errada, adulteração, versão desconhecida,
  esquema inválido e tempo inválido.
- Não aceite criptografia própria, segredo previsível, comparação insegura ou
  serialização que exponha `SecretStr`.
- Mantenha FakeGov explicitamente opt-in e separado do provedor oficial. A
  proibição de credenciais reais aplica-se ao FakeGov, não à integração oficial.
- Não permita credenciais, tokens, chaves ou dados reais de usuários em código,
  fixtures, exemplos, logs ou documentação.

### Arquitetura e compatibilidade

- `govbr_auth/core/` e `govbr_auth/runtime.py` devem permanecer neutros de
  framework: não podem importar FastAPI, Starlette, Django, Flask ou Werkzeug.
- Adaptadores devem preservar os artefatos e ciclos de vida idiomáticos de cada
  framework sem duplicar composição, armazenamento ou regras de domínio.
- Examine mudanças na superfície pública, extras, limites de dependências e
  comportamento nas versões Python 3.11 a 3.14.
- Para mudança observável, verifique testes no nível apropriado, documentação
  pública e `CHANGELOG.md`. Não solicite documentação sem contrato ou convenção
  que a exija.

## Regras de evidência

- Diferencie comportamento observado, inferência e hipótese.
- Prefira caminho de execução direto, teste focal, reprodução mínima ou saída
  de comando a especulação.
- Se faltar evidência, explique a incerteza e a verificação necessária; não a
  converta em defeito confirmado.
- CI verde não prova que uma mudança é correta. Avalie se os testes realmente
  discriminam o risco introduzido.
- Não proponha refatoração ampla quando uma correção localizada resolve a causa.
- Não reporte dívida preexistente que não foi agravada pelo PR.

## Apontamentos

Use uma prioridade por causa raiz:

| Nível | Critério |
| --- | --- |
| `P0` | Exploração, perda de dados ou quebra generalizada imediata |
| `P1` | Defeito grave e provável em fluxo suportado ou limite de segurança |
| `P2` | Defeito concreto com impacto limitado ou dependente de condição válida |
| `P3` | Problema localizado e de baixo impacto que ainda exige correção |

Cada apontamento deve conter:

```md
**[P2] Título objetivo — `caminho/arquivo.py:linha`**

**Problema:** comportamento concreto e cenário em que ocorre.

**Impacto:** contrato, usuário ou proteção afetada.

**Correção:** menor correção ou verificação capaz de resolver a causa.
```

Ancore comentários em linha na menor linha alterada que demonstre o problema.
Use o resumo para problemas entre arquivos, evidência ausente e documentação
faltante. Não use uma linha alterada como pretexto para comentar código não
relacionado.

## Resumo da revisão

Finalize com estas seções, nesta ordem:

1. `### Veredito`: `há apontamentos`, `sem apontamentos` ou
   `evidência insuficiente`.
2. `### Apontamentos`: achados ordenados por prioridade ou declaração explícita
   de ausência.
3. `### Segurança e compatibilidade`: limites relevantes examinados e lacunas.
4. `### Testes e documentação`: cobertura observada, ausências e consistência.
5. `### Checagens e limitações`: comandos realmente executados, resultados e
   verificações não realizadas.
6. `### Arquivos não revisados`: lista justificada ou confirmação de cobertura
   integral.

O veredito descreve o resultado técnico da análise; não equivale a aprovação,
solicitação formal de mudanças ou decisão de merge.

## Erros comuns

| Erro | Conduta correta |
| --- | --- |
| Repetir o checklist do PR | Verificar a alegação no diff, testes ou comandos |
| Comentar apenas estilo | Exigir impacto observável ou regra explícita |
| Sugerir arquitetura futura | Limitar a correção ao risco demonstrado |
| Omitir arquivo sem explicar | Listar a exclusão e a limitação resultante |
| Declarar teste verde sem executá-lo | Informar que a checagem não foi realizada |
| Tratar comentário como bloqueio | Descrever severidade sem decidir o merge |
