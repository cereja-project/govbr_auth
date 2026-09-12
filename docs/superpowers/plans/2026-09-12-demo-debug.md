# Explorador debug da demo — plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** tornar o fluxo FakeGov observável e didático sem alterar sua autenticação.
**Architecture:** captura restrita aos adapters FakeGov; HTTPX observa backchannel;
UI reproduz os eventos saneados, sem reexecutar pedidos no replay.
**Tech Stack:** Python, frameworks existentes, HTML/CSS/JavaScript nativos, pytest,
Chromium/Playwright para verificação local offline, via
`scripts/check_demo_debug_ui.py`.
**Spec:** `docs/superpowers/specs/2026-09-12-demo-debug.md`.

## Global Constraints

Python 3.11–3.14. Sem dependência nova em execução. Sem core alterado, segredos no
trace, delay na autenticação, redução de cobertura, merge, tag ou publicação.

## 1. Captura segura e fronteiras HTTP

Arquivos: `govbr_auth/fake/debug/{redaction,trace,controller,fastapi,django,flask}.py`;
`govbr_auth/{fastapi,django,flask}.py`; `tests/integration/test_demo_debug.py`;
`tests/unit/fake/test_debug_trace.py`.

Interface: `DebugController(application)` guarda a política de demo, configura
hooks HTTPX e resolve os endpoints fixos abaixo de `/govbr-auth-demo/debug`.
`controller.observe(method, path, query, headers, cookies)` abre contexto local;
`observation.finish(status, headers)` fecha um evento sem capturar corpo externo.
`controller.manage(method, headers, cookies)` retorna snapshot seguro e cookie.
`redaction.fields(mapping)` mantém apenas campos permitidos e valores seguros.

- [x] RED: GET da página retorna 200; POST trace inicia captura; outro navegador
  recebe 404; login real produz token/JWKS/UserInfo e nenhum segredo no JSON.
  Comando: `python -m pytest tests/integration/test_demo_debug.py -q`.
- [x] Implementar sanitização e armazenamento limitado antes de hooks/wrappers.
- [x] Ligar captura somente ao perfil fake nos três adapters.
- [x] GREEN: teste focal e suíte; testar origem estrangeira, descarte e limites.

## 2. Apresentação e controle da reprodução

Arquivos: `govbr_auth/fake/debug/presentation.py`,
`govbr_auth/_assets/demo/debug.{html,css,js}`, `govbr_auth/presentation.py`,
`pyproject.toml`, `tests/unit/fake/test_debug_presentation.py`.

Interface: `render_debug_page(login_path)` retorna HTML local com configurações
escapadas; `page_headers(page)` restringe execução ao script próprio. O endpoint
trace fornece `events`, `completed`, `truncated`; a UI não guarda os cookies.

- [x] RED: página exibe switch, diagrama, timeline e painel técnico; usa motion
  reduzido, não contém recursos remotos nem interpolação HTML de dados.
- [x] Implementar controles iniciar, pausar, próxima etapa, replay, velocidade,
  limpar e exportar; destacar informações inferidas e explicar artefatos.
- [x] GREEN: Chromium offline desktop/mobile, teclado, erros de rede e popup
  bloqueado; exportação igual ao trace saneado produzido pelo teste HTTP real.
  A navegação HTTP do Chromium foi bloqueada pela política deste ambiente;
  não foi declarado um teste ponta a ponta de navegador com servidor.

## 3. Distribuição, documentação e entrega

Arquivos: README, CHANGELOG, `docs/guide/demo-debug.rst`, `docs/index.rst`.

- [x] Documentar passos de uso, dados excluídos, limites, replay e dependência #66.
- [x] Executar Black, lint bloqueante e suíte: 980 testes, 100% linhas/branches.
- [x] Build de wheel/sdist; recursos HTML/CSS/JS presentes no wheel instalado.
- [x] Conferir recursos no wheel; script Chromium offline aprovado contra o wheel.
- [ ] Abrir PR contra a branch do #66, registrar evidências e confirmar CI final.

## Evidências locais

Base funcional: PR #66, commit `054ebbdbbeb6146a7d1090fa5ea822b042c38ded`.
Python 3.13.5: 980 testes aprovados, 100% das linhas/branches medidos, zero
lacunas. Black, lint bloqueante, sintaxe JavaScript e build de wheel/sdist
aprovados. O script de UI offline confirmou exportação igual ao trace obtido
pelo cliente HTTP nativo, replay sem novas requisições, teclado, estados de
falha, movimento reduzido e layout móvel sem overflow horizontal.

Comando de reprodução dos controles, com Playwright instalado no ambiente de
validação (não é dependência de execução da biblioteca):

```bash
python scripts/check_demo_debug_ui.py --output /tmp/govbr-demo-ui
```

A integração de navegador com servidor HTTP não foi executada: Chromium
retornou `ERR_BLOCKED_BY_ADMINISTRATOR`. O teste offline não desativa nem
contorna essa política. Os testes HTTP nativos foram executados à parte.
