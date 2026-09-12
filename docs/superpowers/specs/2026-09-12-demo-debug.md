# Demo: explorador didático e técnico do fluxo

## Objetivo aprovado

Adicionar à demo do FakeGov uma opção de modo debug com etapas, animações de
comunicação e painel técnico. O modo normal continua direto e rápido.

## Contratos

- Disponível exclusivamente no perfil FakeGov de FastAPI, Django, Flask e launcher.
- Observação na fronteira HTTP da demo e nos event hooks do cliente HTTPX local;
  nenhum delay, telemetria ou dependência de apresentação no core.
- A reprodução visual é desacelerada, pausável e navegável. A autenticação real
  não aguarda animações: isso evita expirar state, código e prova do navegador.
- Identificar separadamente eventos HTTP observados, verificações inferidas pela
  progressão do core e explicações conceituais. Não inventar tempos por validação.
- A demo confirma a autenticação; não alegar que cria uma sessão da aplicação.
- Nenhum token, state, nonce, código, segredo, verificador, valor de cookie, CPF ou
  perfil pessoal é retido no trace. Sanitização por lista permitida antes de gravar.
  Valores desconhecidos e corpos não estruturados não são persistidos.
- Captura voluntária por navegador, cookie HttpOnly de curta duração e sem Domain;
  leitura exige cookie e header da UI. Mutação exige Origin exato e header próprio.
  Sem CORS, captura global ou acesso a traces por identificador informado na URL.
- Uma captura ativa por navegador/configuração. Memória local limitada a 64 traces,
  128 eventos por trace e dez minutos. Parada remove trace e cookie. Sem persistência.
- Captura por processo: demo local em worker único; sem prometer agregação distribuída.
- UI em português, responsiva, teclado, foco visível, estado em texto, redução de
  movimento, recursos locais e sem CDN/analytics. Nunca usar HTML de eventos.
- Etapas: início, authorize, autenticação no FakeGov, chegada do callback, vínculo
  e state, token, JWKS, aceitação do ID token, UserInfo, resultado e logout.
- Painel: resumo, HTTP (método, rota, parâmetros, status, headers, cookies e corpos
  saneados), artefatos, segurança e eventos. Exportar somente o trace saneado.
- Iniciar pelo popup nativo, preservando o fluxo de autenticação existente. Mostrar
  instruções quando popups estiverem bloqueados. Não embutir provedor em iframe.
- Casos de erro observados ficam visíveis; não adicionar bypass ou fault injection
  no caminho de autenticação para animar falhas.
- Python 3.11–3.14; sem novas dependências de execução; cobertura de linhas/branches
  mantida em 100%; PR dependente do #66, sem merge/tag/publicação.

## Entrega e aceitação

Testes discriminantes de captura real, isolamento entre navegadores, ocultação de
segredos, recusa de origem, limites de memória, erro HTTP e modo desligado; testes
nos três frameworks; inspeção visual desktop/mobile e interação real no Chromium.
