# Simplificação da composição de autenticação Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remover a camada de composição de aplicação e concentrar runtime, serviço e ciclo de vida em um núcleo interno compartilhado pelos adapters FastAPI, Django e Flask.

**Architecture:** `GovBrRuntimeSettings` será a única configuração compartilhada. Um componente interno sem dependências de framework reunirá `RuntimeOwner`, `AuthenticationService` e caminhos resolvidos; os três adapters permanecerão como shells nativos que apenas registram rotas e traduzem respostas. A demo ficará isolada em `govbr_auth.fake`, com `create_fake_app` end-to-end e `create_fake_govbr_app` provider-only.

**Tech Stack:** Python 3.11–3.14, pytest/pytest-asyncio, FastAPI, Django, Flask, httpx, Pydantic, FakeGov, Black, Flake8, build e Twine.

**Spec:** `docs/superpowers/specs/2026-09-04-simplify-auth-composition-design.md`

## Global Constraints

- `govbr_auth/core/` e `govbr_auth/runtime.py` continuam sem imports de FastAPI, Starlette, Django, Flask ou Werkzeug.
- `GovBrRuntimeSettings` será a única configuração compartilhada entre runtime, adapters e FakeGov.
- Não criar adapter base genérico público, `install(app)` universal ou nova camada que apenas agregue flags de apresentação.
- Preservar PKCE exclusivamente com S256, nonce, state criptografado, validação JWT/JWKS, HTTPS fora de loopback e mensagens sem segredos.
- FakeGov continua loopback-only, explicitamente separado do provider oficial e sem credenciais reais versionadas.
- Mudança incompatível autorizada: remover `GovBrApplicationSettings`, `demo_page` dos adapters, `GOVBR_DEMO_PAGE` e a página demo dos adapters.
- Preservar `GovBrAuth` nos módulos `fastapi`, `django` e `flask`, `GovBrRuntime`, `GovBrRuntimeSettings`, `create_govbr_runtime`, `AuthenticationService` e as factories FakeGov existentes.
- Usar `--basetemp` e `cache_dir` fora do repositório; preservar `fake-users.local.json` não rastreado.
- Não publicar PyPI, criar tag, GitHub Release ou fazer push.

---

### Task 1: Congelar o novo contrato público sem `ApplicationSettings`

**Files:**
- Delete: `govbr_auth/application_settings.py`
- Modify: `govbr_auth/runtime.py:11-17`, `govbr_auth/adapters/_runtime.py:29-110`
- Modify: `govbr_auth/fastapi.py:103-133`, `govbr_auth/django.py:38-77`, `govbr_auth/flask.py:36-73`
- Modify: `govbr_auth/fake/fastapi.py:116-149`
- Test: `tests/unit/test_application_settings.py` (delete)
- Test: `tests/unit/test_runtime.py`, `tests/unit/fastapi/test_fastapi_adapter.py`, `tests/unit/django/test_django_adapter.py`, `tests/unit/flask/test_flask_adapter.py`, `tests/unit/fake/test_runtime.py`
- Test: `tests/contract/test_v1_fastapi_contract.py`, `tests/contract/test_v1_public_surface.py`

**Interfaces:**
- Consumes: `GovBrRuntimeSettings`, `GovBrRuntime`, `create_govbr_runtime` e `AuthenticationService` existentes.
- Produces: cada `GovBrAuth` aceitará `settings: GovBrRuntimeSettings | None = None` ou `runtime: GovBrRuntime | None = None`, mas não `GovBrApplicationSettings` nem `demo_page`; `create_fake_app` aceitará `GovBrRuntimeSettings | None`.

- [ ] **Step 1: Escrever os testes RED do contrato removido**

  Substituir os testes que constroem `GovBrApplicationSettings` por testes que expressem o novo uso:

  ```python
  async def success_handler(context: AuthenticationContext) -> Response:
      return Response(status_code=204)
  
  def test_fastapi_uses_runtime_settings_directly() -> None:
      settings = GovBrRuntimeSettings(provider=GovBrProvider.FAKE)
      auth = GovBrAuth(on_success=success_handler, settings=settings)
      assert auth.runtime.provider is GovBrProvider.FAKE
  
  def test_fastapi_demo_page_is_not_an_adapter_argument() -> None:
      with pytest.raises(TypeError, match="unexpected keyword argument 'demo_page'"):
          GovBrAuth(on_success=success_handler, demo_page=True)
  
  def test_application_settings_module_is_removed() -> None:
      assert not (PROJECT_ROOT / "govbr_auth" / "application_settings.py").exists()
  ```

- [ ] **Step 2: Executar somente os testes alterados e confirmar RED**

  Executar:

  ```text
  python -m pytest tests/unit/test_application_settings.py tests/unit/test_runtime.py tests/unit/fastapi/test_fastapi_adapter.py tests/unit/django/test_django_adapter.py tests/unit/flask/test_flask_adapter.py tests/unit/fake/test_runtime.py tests/contract/test_v1_fastapi_contract.py tests/contract/test_v1_public_surface.py --tb=short --disable-warnings -q --basetemp C:\Users\leite\AppData\Local\Temp\govbr_auth_task1_base -o cache_dir=C:\Users\leite\AppData\Local\Temp\govbr_auth_task1_cache
  ```

  Resultado esperado: falha por imports e argumentos ainda pertencentes à API removida; nenhum teste deverá passar apenas por erro de coleta.

- [ ] **Step 3: Implementar a remoção mínima**

  - Remover o import de `GovBrApplicationSettings` de `runtime.py`.
  - Alterar `create_adapter_runtime` para receber `GovBrRuntimeSettings | None` e carregar `GovBrRuntimeSettings.from_environment()` quando ausente.
  - Remover `demo_page` da assinatura e dos retornos de `create_adapter_runtime`.
  - Alterar os três construtores para usar `settings: GovBrRuntimeSettings | None` e eliminar os ramos de registro da página demo.
  - Alterar `create_fake_app` para receber `GovBrRuntimeSettings | None`, exigir `provider == FAKE` e compor diretamente o app end-to-end.
  - Remover `application_settings.py` e atualizar imports de testes e módulos.

- [ ] **Step 4: Executar os testes focais em GREEN**

  Repetir o comando do Step 2. Resultado esperado: todos os testes de contrato e adapters alterados passam, sem `GovBrApplicationSettings` na coleta.

- [ ] **Step 5: Commitar a quebra de contrato isolada**

  ```text
  git add govbr_auth/application_settings.py govbr_auth/runtime.py govbr_auth/adapters/_runtime.py govbr_auth/fastapi.py govbr_auth/django.py govbr_auth/flask.py govbr_auth/fake/fastapi.py tests/unit/test_application_settings.py tests/unit/test_runtime.py tests/unit/fastapi/test_fastapi_adapter.py tests/unit/django/test_django_adapter.py tests/unit/flask/test_flask_adapter.py tests/unit/fake/test_runtime.py tests/contract/test_v1_fastapi_contract.py tests/contract/test_v1_public_surface.py
  git commit -m "refactor(adapters): remove application settings layer"
  ```

### Task 2: Extrair o núcleo interno comum dos adapters

**Files:**
- Create: `govbr_auth/adapters/_application.py`
- Modify: `govbr_auth/adapters/_runtime.py:29-90`
- Modify: `govbr_auth/fastapi.py:43-100`, `govbr_auth/fastapi.py:103-190`
- Modify: `govbr_auth/django.py:38-164`
- Modify: `govbr_auth/flask.py:36-158`
- Test: `tests/unit/adapters/test_application.py`
- Test: `tests/contract/test_framework_import_boundaries.py`

**Interfaces:**
- Consumes: `GovBrRuntimeSettings | None`, `GovBrRuntime | None`, `AuthenticationService`, `RuntimeOwner`, `FakeGovHttpTransport` factory e `clock`.
- Produces: `AdapterApplication` com os atributos `owner`, `service`, `login_path`, `callback_path`, `clock`; a função `create_adapter_application` retorna `AdapterApplication`.

  Assinatura mínima:

  ```python
  @dataclass(slots=True)
  class AdapterApplication:
      owner: RuntimeOwner
      service: AuthenticationService
      login_path: str
      callback_path: str
      clock: Callable[[], datetime]
  
  def create_adapter_application(
      *,
      settings: GovBrRuntimeSettings | None,
      runtime: GovBrRuntime | None,
      expose_tokens: bool,
      prefix: str,
      clock: Callable[[], datetime],
      user_repository: FakeUserRepository | None,
      fake_transport_factory: Callable[[FakeGovSimulator], httpx.AsyncBaseTransport],
  ) -> AdapterApplication:
      raise NotImplementedError
  ```

- [ ] **Step 1: Escrever testes RED para a composição única**

  Criar `tests/unit/adapters/test_application.py` com casos que verifiquem uma única instância de serviço, caminhos calculados e ownership:

  ```python
  def fake_settings() -> GovBrRuntimeSettings:
      return GovBrRuntimeSettings(provider=GovBrProvider.FAKE)
  
  def fixed_clock() -> datetime:
      return datetime(2026, 1, 1, tzinfo=UTC)
  
  def transport_factory(fake: FakeGovSimulator) -> httpx.AsyncBaseTransport:
      return FakeGovHttpTransport(fake, clock=fixed_clock)

  def build_runtime() -> GovBrRuntime:
      return create_govbr_runtime(
          fake_settings(),
          fake_transport_factory=transport_factory,
          clock=fixed_clock,
      )
  
  def test_create_adapter_application_builds_one_shared_service() -> None:
      application = create_adapter_application(
          settings=fake_settings(), runtime=None, expose_tokens=False,
          prefix="/auth/govbr", clock=fixed_clock,
          user_repository=None, fake_transport_factory=transport_factory,
      )
      assert isinstance(application.service, AuthenticationService)
      assert application.login_path == "/auth/govbr/login"
      assert application.callback_path == "/auth/govbr/callback"
  
  def test_borrowed_runtime_is_not_closed_by_application() -> None:
      runtime = build_runtime()
      application = create_adapter_application(
          settings=None, runtime=runtime, expose_tokens=False,
          prefix="/auth/govbr", clock=fixed_clock,
          user_repository=None, fake_transport_factory=transport_factory,
      )
      application.owner.close()
      assert runtime.is_closed is False
  ```

- [ ] **Step 2: Executar o teste novo e confirmar RED**

  ```text
  python -m pytest tests/unit/adapters/test_application.py -v --basetemp C:\Users\leite\AppData\Local\Temp\govbr_auth_task2_base -o cache_dir=C:\Users\leite\AppData\Local\Temp\govbr_auth_task2_cache
  ```

  Resultado esperado: falha porque `AdapterApplication` e `create_adapter_application` ainda não existem.

- [ ] **Step 3: Implementar o núcleo mínimo**

  Mover para `_application.py` somente a criação de `AuthenticationService`, a resolução de `login_path`/`callback_path` e a retenção de `RuntimeOwner`. Não mover tipos de resposta nem imports de frameworks. Reutilizar `create_adapter_runtime` para validação e ownership, sem criar uma nova hierarquia de adapters.

- [ ] **Step 4: Migrar os três adapters**

  Cada construtor chamará a mesma factory. Os handlers usarão apenas
  `application.service.authorization_url(now=application.clock())` e
  `await application.service.authenticate(code=code, state=state,
  now=application.clock())`; a diferença restante será exclusivamente:

  ```python
  # FastAPI
  return RedirectResponse(authorization.url, status_code=302)
  
  # Django
  return HttpResponseRedirect(authorization.url)
  
  # Flask
  return redirect(authorization.url)
  ```

  Manter os callbacks e conversores de erro nativos de cada framework.

- [ ] **Step 5: Executar regressão focal dos três adapters**

  ```text
  python -m pytest tests/unit/adapters tests/unit/fastapi/test_fastapi_adapter.py tests/unit/django/test_django_adapter.py tests/unit/flask/test_flask_adapter.py tests/integration/fastapi/test_auth_flow.py tests/integration/django/test_django_fake_flow.py tests/integration/flask/test_flask_fake_flow.py --tb=short --disable-warnings -q --basetemp C:\Users\leite\AppData\Local\Temp\govbr_auth_task2_regression -o cache_dir=C:\Users\leite\AppData\Local\Temp\govbr_auth_task2_cache
  ```

  Resultado esperado: todas as rotas e lifecycle existentes passam; nenhuma regra OAuth/OIDC muda.

- [ ] **Step 6: Commitar a extração**

  ```text
  git add govbr_auth/adapters govbr_auth/fastapi.py govbr_auth/django.py govbr_auth/flask.py tests/unit/adapters tests/contract/test_framework_import_boundaries.py
  git commit -m "refactor(adapters): centralize authentication composition"
  ```

### Task 3: Separar definitivamente o launcher FakeGov da demo consumidora

**Files:**
- Modify: `govbr_auth/fake/fastapi.py:116-163`, `govbr_auth/fake/launcher.py:22-84`
- Modify: `govbr_auth/fake/__init__.py`, `govbr_auth/fake/__main__.py`
- Modify: `tests/integration/test_fake_launcher.py`, `tests/unit/fake/test_runtime.py`, `tests/contract/test_v1_fake_provider_contract.py`

**Interfaces:**
- Consumes: `GovBrRuntimeSettings`, `create_govbr_runtime`, `create_fake_govbr_app`, `create_end_to_end_app` e o novo `AdapterApplication` via `GovBrAuth`.
- Produces: `create_fake_app(settings: GovBrRuntimeSettings | None = None, *, clock: Callable[[], datetime] = utc_now, user_repository: FakeUserRepository | None = None) -> FastAPI` sempre end-to-end; `create_fake_govbr_app(runtime: FakeGovSimulator | FakeGovBrProvider, *, application: FakeGovHttpApplication | None = None, credential_authenticator: FakeCredentialAuthenticator | None = None, automatic_subject: str | None = None, clock: Callable[[], datetime] = utc_now) -> FastAPI` continua provider-only.

- [ ] **Step 1: Escrever testes RED para os dois perfis explícitos**

  ```python
  def fake_settings() -> GovBrRuntimeSettings:
      return GovBrRuntimeSettings(provider=GovBrProvider.FAKE)
  
  def fixed_clock() -> datetime:
      return datetime(2026, 1, 1, tzinfo=UTC)

  def fake_runtime_settings() -> GovBrRuntimeSettings:
      return GovBrRuntimeSettings(provider=GovBrProvider.FAKE)

  def route_paths(application: FastAPI) -> set[str]:
      return {
          route.path
          for route in application.routes
          if isinstance(getattr(route, "path", None), str)
      }
  
  def test_create_fake_app_exposes_demo_and_consumer_routes() -> None:
      app = create_fake_app(fake_settings())
      paths = route_paths(app)
      assert "/govbr-auth-demo" in paths
      assert "/auth/govbr/login" in paths
      assert "/fake-govbr/authorize" in paths
  
  def test_create_fake_govbr_app_does_not_expose_consumer_demo() -> None:
      runtime = create_fake_gov_simulator(fake_runtime_settings(), prefix="", clock=fixed_clock)
      app = create_fake_govbr_app(runtime)
      assert "/govbr-auth-demo" not in route_paths(app)
  ```

- [ ] **Step 2: Executar os testes FakeGov e confirmar RED**

  ```text
  python -m pytest tests/integration/test_fake_launcher.py tests/unit/fake/test_runtime.py tests/contract/test_v1_fake_provider_contract.py -v --basetemp C:\Users\leite\AppData\Local\Temp\govbr_auth_task3_base -o cache_dir=C:\Users\leite\AppData\Local\Temp\govbr_auth_task3_cache
  ```

- [ ] **Step 3: Implementar a separação**

  - Remover `GovBrApplicationSettings` e `GOVBR_DEMO_PAGE` de `_launcher_settings`.
  - Fazer `run()` carregar somente `GovBrRuntimeSettings`, defaulting `GOVBR_PROVIDER` para `fake` no entry point.
  - Fazer `create_fake_app` construir o runtime consumidor fake uma vez e chamar `create_end_to_end_app`.
  - Registrar `/govbr-auth-demo` dentro de `create_end_to_end_app`, fora de `GovBrAuth`.
  - Manter `create_fake_govbr_app` como provider-only e sem página consumidora.

- [ ] **Step 4: Executar o fluxo FakeGov completo**

  ```text
  python -m pytest tests/integration/test_fake_launcher.py tests/integration/fake tests/unit/fake tests/contract/test_v1_fake_provider_contract.py --tb=short --disable-warnings -q --basetemp C:\Users\leite\AppData\Local\Temp\govbr_auth_task3_regression -o cache_dir=C:\Users\leite\AppData\Local\Temp\govbr_auth_task3_cache
  ```

- [ ] **Step 5: Commitar os perfis do launcher**

  ```text
  git add govbr_auth/fake tests/integration/test_fake_launcher.py tests/unit/fake tests/contract/test_v1_fake_provider_contract.py
  git commit -m "refactor(fake): isolate end-to-end launcher"
  ```

### Task 4: Reescrever documentação e exemplos para o caminho curto

**Files:**
- Modify: `README.md`
- Modify: `docs/guide/quick-start.rst`, `docs/guide/fake-mode.rst`, `docs/guide/configuration.rst`, `docs/guide/troubleshooting.rst`
- Modify: `docs/api/fastapi.rst`, `docs/api/django.rst`, `docs/api/flask.rst`, `docs/api/fake-govbr.rst`
- Modify: `examples/example_fastapi.py`, `examples/example_django.py`, `examples/example_flask.py`, `examples/example_settings.py`, `.env.example`, `CHANGELOG.md`
- Test: `tests/integration/test_readme_quickstart.py`, `tests/integration/test_documented_framework_quickstarts.py`, `tests/contract/test_documentation_surface.py`, `tests/integration/test_example_fastapi.py`

**Interfaces:**
- Consumes: `GovBrAuth(on_success=authenticated)`, `GovBrAuth(settings=runtime_settings, on_success=authenticated)`, `create_fake_app()` e `create_fake_govbr_app(runtime)`.
- Produces: quickstarts copiáveis que não importam `GovBrApplicationSettings`, não usam `demo_page` e não dependem de `GOVBR_DEMO_PAGE`.

- [ ] **Step 1: Escrever testes RED de documentação**

  Atualizar os testes de superfície para exigir:

  ```python
  assert "GovBrApplicationSettings" not in public_docs
  assert "GOVBR_DEMO_PAGE" not in public_docs
  assert "demo_page" not in adapter_api_docs
  assert "auth = GovBrAuth(on_success=authenticated)" in readme
  assert "create_fake_app" in fake_mode_docs
  ```

- [ ] **Step 2: Executar os testes documentais e confirmar RED**

  ```text
  python -m pytest tests/integration/test_readme_quickstart.py tests/integration/test_documented_framework_quickstarts.py tests/contract/test_documentation_surface.py tests/integration/test_example_fastapi.py -v --basetemp C:\Users\leite\AppData\Local\Temp\govbr_auth_task4_base -o cache_dir=C:\Users\leite\AppData\Local\Temp\govbr_auth_task4_cache
  ```

- [ ] **Step 3: Reescrever o quickstart mínimo**

  O bloco FastAPI deverá conter somente:

  ```python
  from fastapi import FastAPI
  from fastapi.responses import JSONResponse
  from govbr_auth.fastapi import AuthContext, GovBrAuth
  
  async def authenticated(context: AuthContext) -> JSONResponse:
      return JSONResponse({"authenticated": True})
  
  app = FastAPI()
  auth = GovBrAuth(on_success=authenticated)
  app.include_router(auth.router)
  ```

  O `.env` configurará `GOVBR_PROVIDER=fake` e `GOVBR_FAKE_USERS_FILE`; a página `/govbr-auth-demo` será explicada como recurso exclusivo do `python -m govbr_auth.fake`, não como rota do adapter.

- [ ] **Step 4: Atualizar Django, Flask, exemplos e documentação de configuração**

  Remover imports e trechos de `GovBrApplicationSettings`, `demo_page` e `GOVBR_DEMO_PAGE`. Em cada framework, manter apenas a montagem nativa (`urlpatterns = auth.urlpatterns`, `auth.register(app)` ou `app.include_router(auth.router)`).

- [ ] **Step 5: Executar os testes documentais em GREEN**

  Repetir o comando do Step 2. Resultado esperado: snippets do README e guias importam em diretório vazio, sem carregar `.env` ancestral e sem exigir checkout do projeto.

- [ ] **Step 6: Commitar documentação e exemplos**

  ```text
  git add README.md docs examples .env.example CHANGELOG.md tests/integration/test_readme_quickstart.py tests/integration/test_documented_framework_quickstarts.py tests/contract/test_documentation_surface.py tests/integration/test_example_fastapi.py
  git commit -m "docs: simplify framework quickstarts"
  ```

### Task 5: Fechar contratos, distribuição e revisão independente

**Files:**
- Modify: `tests/contract/test_v1_public_surface.py`, `tests/contract/test_v1_dependency_contract.py`, `tests/contract/test_refactoring_boundaries.py`
- Modify: `requirements-dev.txt` somente se necessário para declarar `setuptools>=84.0.0`
- Review: diff completo desde o commit da especificação

**Interfaces:**
- Consumes: todos os componentes e contratos das Tasks 1–4.
- Produces: suíte e artefatos de distribuição verificáveis; nenhum símbolo removido permanece em código, docs ou exemplos.

- [ ] **Step 1: Adicionar verificações finais discriminantes**

  Incluir contratos que falhem se os símbolos antigos retornarem:

  ```python
  def test_removed_application_configuration_is_absent() -> None:
      import inspect
      import govbr_auth.runtime
      from govbr_auth.fastapi import GovBrAuth
  
      assert not hasattr(govbr_auth.runtime, "GovBrApplicationSettings")
      assert "demo_page" not in inspect.signature(GovBrAuth).parameters
  
  def test_shared_adapter_module_is_framework_neutral() -> None:
      source = (PROJECT_ROOT / "govbr_auth" / "adapters" / "_application.py").read_text()
      assert not re.search(r"from (fastapi|django|flask|werkzeug|starlette)", source)
  ```

- [ ] **Step 2: Provisionar a dependência de build e verificar ambiente**

  Executar no ambiente virtual do projeto:

  ```text
  python -m pip install -r requirements-dev.txt
  python -m pip check
  python -c "import setuptools; assert tuple(map(int, setuptools.__version__.split('.')[:2])) >= (84, 0)"
  ```

  Se o ambiente exigir acesso à rede, solicitar aprovação antes de instalar; não alterar o teste de build para esconder a ausência de `setuptools`.

- [ ] **Step 3: Executar a suíte completa**

  ```text
  python -m pytest --tb=short --disable-warnings -q --basetemp C:\Users\leite\AppData\Local\Temp\govbr_auth_final_base -o cache_dir=C:\Users\leite\AppData\Local\Temp\govbr_auth_final_cache
  ```

  Resultado esperado: zero falhas e zero erros de coleta.

- [ ] **Step 4: Executar formatação, lint e distribuição**

  ```text
  python -m black --check govbr_auth tests examples scripts
  python -m flake8 govbr_auth tests examples scripts --count --select=E9,F63,F7,F82 --show-source --statistics
  python -m build --no-isolation --outdir C:\Users\leite\AppData\Local\Temp\govbr_auth_dist
  python -m twine check C:\Users\leite\AppData\Local\Temp\govbr_auth_dist\*
  python scripts/verify_distribution.py C:\Users\leite\AppData\Local\Temp\govbr_auth_dist\*.whl
  ```

- [ ] **Step 5: Fazer revisão independente do diff**

  Solicitar revisão com base no commit anterior à Task 1 e no `HEAD`, cobrindo:

  - duplicação residual de composição entre adapters e FakeGov;
  - imports indevidos no núcleo compartilhado;
  - lifecycle de runtime criado versus emprestado;
  - regressões de callback, prefixo, PKCE, nonce, state, JWT/JWKS e mensagens seguras;
  - documentação executável e compatibilidade deliberadamente quebrada.

  Corrigir achados críticos/importantes, executar novamente os testes afetados e registrar o resultado antes de concluir.

- [ ] **Step 6: Conferir estado Git e preparar integração local**

  ```text
  git status --short
  git diff --check HEAD~5..HEAD
  git log --oneline -6
  ```

  Confirmar que `fake-users.local.json` continua não rastreado, que não há credenciais versionadas e que nenhuma operação remota foi executada.
