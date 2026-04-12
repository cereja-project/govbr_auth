# AGENTS.md: Essential Context for AI Agents

## Project Overview

**govbr-auth** is a Python OAuth 2.0 + PKCE authentication library for integrating with Gov.br (Brazilian government
login). It supports FastAPI, Flask, Django, and custom stacks with a built-in fake mode for local development.

**Stack**: Python 3.8+, Pydantic v1+, httpx (async/sync), PyJWT, cryptography (Fernet), Black (code formatter), pytest (
asyncio), optional framework integrations (FastAPI, Flask, Django)

**Key dependency**: `cereja` (utilities, versioning)

---

## Architecture: Core Components

### 1. **Core Logic** (`govbr_auth/core/`)

**`config.py`** - Configuration container

- Pydantic model `GovBrConfig`: All OAuth parameters, URLs, secrets, JWT settings
- **Required fields**: `client_id`, `client_secret`, `redirect_uri`, `cript_verifier_secret`, `govbr_auth_url`,
  `govbr_token_url`
- **Key validation**:
    - `cript_verifier_secret` must be valid 32-byte Fernet key (exactly 44 chars base64) → raises `ValueError` if not
    - `authorize_endpoint`, `authenticate_endpoint`, `prefix` stripped of leading/trailing slashes
- **Mode detection**: `use_fake` flag has priority over env var
- **Environment**: `USE_FAKE_GOVBR` (case-insensitive, accepts: `true/1/yes/y`)
- **Factory method**: `GovBrConfig.from_env()` loads from `.env`, raises `ValueError` if required vars missing
- **Defaults**: OAuth scope = `openid profile email`, response_type = `code`, code_challenge_method = `S256`

**`govbr.py`** - OAuth 2.0 PKCE implementation

- **`GovBrAuthorize`**: Generates authorization URL with code challenge (S256)
    - `build_authorize_url()` → returns dict `{"url": "..."}` with full OAuth URL
    - Encrypts 80-byte random `code_verifier` (base64, alphanumeric only) with Fernet → stores in `state` param
    - Generates random `nonce` (32-byte urlsafe) for token verification
    - Returns S256 code challenge (SHA256 hash, base64 without padding)
    - Raises `GovBrException` on generation failures

- **`GovBrIntegration`**: Exchanges code for token, decodes JWT
    - **Async**: `async_exchange_code_for_token(code, state)` → uses httpx.AsyncClient
    - **Sync**: `exchange_code_for_token_sync(code, state)` → uses httpx.Client
    - **Request building**: Decrypts state → recovers code_verifier → builds token POST with Basic auth
    - **JWT handling**: Priority chain with fallback:
        1. **JWKS (production/staging)**: Detects known Gov.br issuer URLs → uses RSA public keys
        2. **jwt_secret (local/fake)**: HS256 verification with configured secret
        3. **Unverified decode (dev only)**: Skips signature check, logs warning
    - **Response parsing**: Validates HTTP success → checks `id_token` presence → decodes payload
    - **Decryption error handling**: Raises `ValueError("Invalid or missing code_verifier")` if state decryption fails
    - **Returns**: `{"token": token_json, "id_token_decoded": decoded_payload}`

- **Exceptions**: `GovBrException` (base), `GovBrAuthenticationError` (extends base)

### 2. **Framework Connectors** (`controller.py`)

**`GovBrConnector`** - Single entry point for all frameworks

- **Initialization**: Takes config, prefix, endpoint names, optional callback, optional fake users
- **Auto-initialization**: Detects fake mode in constructor → initializes FakeGovBrService automatically
- **Fake mode detection order**:
    1. Check explicit `use_fake=True` in config
    2. Parse both `govbr_auth_url` and `govbr_token_url` for localhost/127.0.0.1
    3. If either is local, activate fake mode (backward compatibility)
- **Callback handling**: `on_auth_success(result, request)` called after token exchange
    - Can return sync value or coroutine (FastAPI awaits automatically)
    - Input: `result = {"token": {...}, "id_token_decoded": {...}}`
- **Error handling pattern**:
    - `GovBrException` → HTTP 400 (config/generation error)
    - `GovBrAuthenticationError` → HTTP 401 (token/auth failure)

**Framework-specific initialization**:

- **FastAPI** (`init_fastapi(app)`):
    - Uses `APIRouter` with prefix
    - Handlers are async
    - Returns `{"url": "..."}` from authorize endpoint
    - POST accepts JSON body with `code`, `state`
    - If fake mode: extracts path from URL, registers fake router

- **Flask** (`init_flask(app)`):
    - Uses `Blueprint` with url_prefix
    - Handlers are sync
    - `code`, `state` from query params (not body)
    - Returns `jsonify()` with same structure
    - If fake mode: extracts path from URL string parsing

- **Django** (`init_django()`):
    - Returns list of URL patterns (not modifying URL config)
    - `code`, `state` from POST data
    - Views are class-based, dispatch pattern
    - If fake mode: not yet implemented (no fake endpoints for Django)

### 3. **Fake Development Server** (`fake_govbr.py`)

**`FakeGovBrService`** - Simulates Gov.br OAuth flow

- Issues fake codes/tokens signed with `jwt_secret`
- Tracks sessions in-memory (`_SESSION_DATA`)
- Methods: `exchange_code_for_token()`, generates valid JWT tokens

**`FakeUserData`** - Test user model (CPF, nome, email, picture)

- Default users via `create_default_fake_users()` (3 pre-configured users)
- Password = CPF always

**Fake endpoints (auto-registered)**:

- `GET /fake-govbr/authorize` → HTML login form
- `POST /fake-govbr/login` → processes CPF/password → redirects with code+state
- `POST /fake-govbr/token` → exchanges code for JWT
- `GET /fake-govbr/users` → lists available test users

---

## Critical Data Flows

### Happy Path: Real Gov.br Authentication

```
1. Frontend: GET /auth/govbr/authorize
   ↓
2. Backend: GovBrAuthorize.build_authorize_url()
   - generates random code_verifier (80 bytes)
   - encrypts it with Fernet (cript_verifier_secret)
   - puts encrypted value in 'state' param
   - generates code_challenge (SHA256 of verifier)
   - returns full OAuth URL
   ↓
3. Frontend: redirects user to Gov.br with state + challenge
   ↓
4. Gov.br: authenticates user, returns code + state to redirect_uri
   ↓
5. Frontend: POST /auth/govbr/authenticate with code + state
   ↓
6. Backend: GovBrIntegration.exchange_code_for_token(code, state)
   - decrypts state to get code_verifier
   - builds POST to Gov.br token endpoint with Basic auth
   - includes code_verifier (PKCE proof)
   - receives id_token (JWT)
   ↓
7. Backend: jwt_payload_decode(id_token)
   - tries JWKS if issuer is known Gov.br
   - falls back to jwt_secret if available
   - last resort: unverified decode (logs warning)
   - returns decoded payload with user claims
   ↓
8. Backend: calls on_auth_success(result, request)
   - result = {"token": {...}, "id_token_decoded": {...}}
   - callback can transform/store data
   ↓
9. Frontend: receives authenticated user data
```

### Fake Mode Flow (Development)

```
1. Config: use_fake=True or USE_FAKE_GOVBR=true
   ↓
2. GovBrConnector.__init__()
   - detects fake mode
   - initializes FakeGovBrService
   - logs activation
   ↓
3. init_fastapi/init_flask/init_django()
   - registers standard /auth/govbr/* endpoints
   - if fake mode: also registers /fake-govbr/* routes
   ↓
4. Frontend: GET /fake-govbr/authorize
   - renders HTML login form (pre-configured users)
   ↓
5. User: enters CPF + password (CPF in both fields)
   - POST /fake-govbr/login
   - redirects with fake code + state
   ↓
6. Frontend: POST /auth/govbr/authenticate with code + state
   - state is plain (not encrypted in fake mode)
   - code is lookup key in FakeGovBrService
   ↓
7. Backend: FakeGovBrService.exchange_code_for_token()
   - looks up session
   - generates JWT signed with jwt_secret
   - returns token + decoded payload
   ↓
8. Rest of flow same as real (callback, response, etc)
```

### State Parameter Lifecycle

```
ENCRYPTION (frontend → backend):
- GovBrAuthorize: code_verifier → Fernet.encrypt() → base64 string → URL state param
- Frontend: stores state param in redirect

DECRYPTION (backend → token exchange):
- GovBrIntegration: receives state param from frontend
- Calls __decrypt_code_verifier(state)
- If Fernet fails: raises ValueError("Invalid or missing code_verifier")
- If success: code_verifier available for PKCE proof

KEY POINT: State is encrypted ONLY during real mode.
In fake mode, state is handled directly by FakeGovBrService (no encryption needed).
```

---

## Error Handling Pattern

### Exception Hierarchy

```
GovBrException
├── GovBrAuthenticationError (extends GovBrException)
└── (other GovBrExceptions for config/generation errors)
```

### Where Errors Happen & How They're Caught

| Component                                    | Error Type               | Cause                                                              | HTTP Code       |
|----------------------------------------------|--------------------------|--------------------------------------------------------------------|-----------------|
| `GovBrConfig` init                           | ValueError               | Fernet key invalid, missing env vars                               | ❌ (setup error) |
| `GovBrAuthorize.build_authorize_url()`       | GovBrException           | Rare: encoding/crypto failure                                      | 400             |
| `__encrypt_code_verifier()`                  | GovBrException           | Fernet encryption fails                                            | 400             |
| `__decrypt_code_verifier()`                  | ValueError               | Fernet decrypt fails (wrong state or corrupted)                    | 401             |
| `GovBrIntegration.exchange_code_for_token()` | GovBrAuthenticationError | HTTP error from Gov.br, missing id_token                           | 401             |
| `jwt_payload_decode()`                       | GovBrAuthenticationError | JWT verification fails (bad signature, expired, audience mismatch) | 401             |

### Controller Catch Pattern

```python
# FastAPI / Flask / Django all follow:
try:
    result = integration.exchange_code_for_token(code, state)
except GovBrException:  # catches both base and AuthenticationError
    return HTTP
    400 or 401(depending
    on
    error
    type)
```

### Key Error Messages

- `"Invalid or missing code_verifier"` → State decryption failed → likely stale/tampered state
- `"JWT signature verification failed"` → Token invalid → likely fake token or wrong env
- `"Token de ID não encontrado na resposta"` → Gov.br returned token without id_token → likely config error

### Testing Error Paths

- Mock `httpx.post()` to return 401, 500, missing fields
- Test state decryption with invalid/empty strings
- Test JWT verification with invalid signatures
- Use `pytest.raises(GovBrAuthenticationError)` to verify exceptions

---

## Project Conventions & Patterns

### Code Style

- **PEP 8**: Enforced via Black (present in dev deps)
- **Type hints**: Used throughout core logic, Pydantic for validation
- **Error handling**: Specific exceptions (`GovBrException`, `GovBrAuthenticationError`), caught at controller level
- **Logging**: Uses standard `logging` module, minimal but present in fake mode detection

### Testing Strategy (pytest)

- **Location**: `tests/` directory
- **Test files**: One per major component (`test_config_and_errors.py`, `test_jwt_verification.py`, etc.)
- **Framework tests**: Separate test files for FastAPI, Flask, Django integration
- **Async support**: `pytest-asyncio` configured (`pytest.ini` with `asyncio_default_fixture_loop_scope = function`)
- **Pattern**: Direct assertions, no mocking unless necessary

### Configuration Hierarchy

1. Explicit parameters to `GovBrConfig()` (highest priority)
2. Environment variables (`.env` auto-loaded via `python-dotenv`)
3. Defaults in config class (lowest priority)

### Fake Mode Activation Logic

- **Primary**: Config flag `use_fake=True`
- **Secondary**: `USE_FAKE_GOVBR` env var = `true/1/yes/y`
- **Heuristic**: URLs pointing to localhost/127.0.0.1 (preserved for compatibility)

---

## Key Files & Their Responsibility

| File                              | Purpose                                               | Key Classes/Functions                                                                | Critical Validations                                   |
|-----------------------------------|-------------------------------------------------------|--------------------------------------------------------------------------------------|--------------------------------------------------------|
| `govbr_auth/core/config.py`       | Configuration validation + loading                    | `GovBrConfig`, `GovBrConfig.from_env()`                                              | Fernet key format (44 chars), required env vars        |
| `govbr_auth/core/govbr.py`        | OAuth 2.0 PKCE core logic (authorize, token exchange) | `GovBrAuthorize`, `GovBrIntegration`, `GovBrException`, `GovBrAuthenticationError`   | State encryption/decryption, JWT verification priority |
| `govbr_auth/controller.py`        | Framework adapters + fake endpoint registration       | `GovBrConnector`, `GovBrConnector.init_fastapi()`, `.init_flask()`, `.init_django()` | Error mapping to HTTP status codes, callback awaiting  |
| `govbr_auth/fake_govbr.py`        | Mock Gov.br service + login UI                        | `FakeGovBrService`, `FakeUserData`, `create_default_fake_users()`                    | Session tracking, JWT token generation                 |
| `govbr_auth/utils.py`             | Helper functions                                      | `generate_cript_verifier_secret()`                                                   | Fernet key generation                                  |
| `govbr_auth/__init__.py`          | Public API exports                                    | All public classes and functions                                                     | Import order matters (cereja dependency)               |
| `tests/`                          | Pytest test suite                                     | Framework-specific + core logic tests                                                | Async support configured in `pytest.ini`               |
| `.github/copilot-instructions.md` | Developer instructions for AI agents                  | Guidelines and rules                                                                 | Knowledge governance                                   |
| `.github/learn-patterns.md`       | Consolidated project knowledge                        | Validated patterns, decisions, errors, heuristics                                    | Updated based on evidence                              |
| `.github/knowledge-candidates.md` | Queue of potential knowledge entries                  | Candidate patterns, decisions, errors, heuristics                                    | Requires validation before promotion                   |
| `.github/agents/`                 | AI agent definitions for tasks                        | Bugfix, backend implementer, etc.                                                    | Task-specific instructions                             |

---

## Common Development Tasks

### Run Tests

```bash
pytest tests/
```

### Run Example App

```bash
USE_FAKE_GOVBR=true uvicorn examples.example_simple_app:app --reload
```

### Generate Fernet Key (for `cript_verifier_secret`)

```python
from govbr_auth.utils import generate_cript_verifier_secret

print(generate_cript_verifier_secret())
```

### Add New Framework Support

1. Create `init_<framework>()` method in `GovBrConnector`
2. Register OAuth endpoints (`/authorize`, `/authenticate`)
3. If fake mode: register fake endpoints too (extract path from config URLs)
4. Add tests in `tests/test_<framework>_auth.py`

---

## Critical Implementation Details

### State Parameter Security

- State contains **encrypted** `code_verifier` (not plain)
- Uses Fernet symmetric encryption with `cript_verifier_secret`
- Decrypted during token exchange - must not fail silently
- **Flow**: Generate 80-byte random verifier → base64 encode → Fernet encrypt → URL-encode → store in state param
- **Recovery**: URL-decode state → Fernet decrypt → recover verifier for PKCE proof
- **Validation**: Fernet key must be exactly 44 chars (32 bytes base64 encoded)

### JWT Verification Priority

For `id_token` decoding:

1. **JWKS endpoint** (production/staging): Detects known Gov.br issuer URLs → uses RSA public keys → verifies audience
2. **jwt_secret** (local/fake): HS256 verification with configured secret → verifies expiration
3. **Unverified decode** (dev only): Skips signature check, logs WARNING level message → use only in local development

**Key point**: Each strategy has different audience/exp validation rules. Switching strategies mid-deployment risks
accepting invalid tokens.

### Async/Sync Dual Support

- Core classes support both: `build_authorize_url()` / `build_authorize_url_sync()`
- Controllers adapt to framework: FastAPI (async handlers), Flask (sync handlers), Django (both)
- Exchange methods: `async_exchange_code_for_token()` / `exchange_code_for_token_sync()`
- **httpx usage**: AsyncClient for async, Client for sync (not mixed in same method)
- **Callback handling**: Controller detects if callback returns coroutine with `asyncio.iscoroutine()` and awaits
  automatically

### Fake Users Data Structure

```python
{
    "12345678901": FakeUserData(
            cpf="12345678901",
            nome="João da Silva",
            email="joao.silva@example.com",
            picture="..."  # optional
    ),
    ...
}
```

- **Default users**: 3 pre-configured users via `create_default_fake_users()`
- **Password rule**: Always equals CPF value
- **Session tracking**: Stored in module-level `_SESSION_DATA` dict (in-memory, lost on restart)
- **JWT signing**: Uses `fake_jwt_secret` parameter (default: "fake-govbr-dev-secret")

### Configuration Loading Priority

```
1. Explicit GovBrConfig() constructor params (highest)
2. Environment variables via .env (python-dotenv auto-loads)
3. Defaults in GovBrConfig class definition (lowest)
```

### Framework Endpoint Registration Pattern

- **Path extraction**: Each framework extracts base path from configured URLs differently:
    - FastAPI: Uses `urlparse()` to get path components
    - Flask: String split on `://` and `/`
    - Django: Simple string parsing (not yet implemented for fake mode)
- **Registration timing**: Fake endpoints registered immediately in `init_<framework>()` if `is_fake_mode=True`
- **Route isolation**: Fake endpoints use separate router/blueprint to avoid conflicts with main auth endpoints

### Real ↔ Fake Mode Switching

**From real to fake** (for testing):

1. Set `USE_FAKE_GOVBR=true` in `.env` or pass `use_fake=True` to `GovBrConfig()`
2. Update URLs to point to localhost endpoints: `http://localhost:8000/fake-govbr/authorize` etc
3. Set `jwt_secret` to match what fake service will use (default: "fake-govbr-dev-secret")
4. Fake endpoints auto-register on `init_fastapi/init_flask` call
5. Token encryption/decryption logic bypassed (state not encrypted in fake mode)

**From fake to real** (for production):

1. Set `USE_FAKE_GOVBR=false` (or omit) in production `.env`
2. Update URLs to production Gov.br endpoints: `https://sso.acesso.gov.br/authorize` etc
3. Remove mock users (pass real user pool or None)
4. Ensure `cript_verifier_secret` is set to a valid Fernet key (44 chars base64)
5. JWT verification switches to JWKS lookup (RSA keys from Gov.br)
6. State parameter becomes encrypted for CSRF protection

**Key gotchas**:

- Changing `cript_verifier_secret` breaks existing sessions (state decryption fails)
- JWT verification strategy determines which `audience` and `exp` claims are validated
- Fake mode state is plain (no encryption); real mode state is Fernet-encrypted
- Session data lost on server restart in fake mode (in-memory storage)

---

## Integration Checklist for New Features

### 1. **State Decryption Failure**

- **Symptom**: Random "Invalid or missing code_verifier" errors
- **Root cause**: Different `cript_verifier_secret` between authorization and token exchange
- **Prevention**: Verify `cript_verifier_secret` is identical across all deployment environments
- **Test**: Create state with one secret, try decrypting with another → should fail

### 2. **Fake Mode Leaking to Production**

- **Symptom**: Real Gov.br URLs suddenly stop working
- **Root cause**: `use_fake=True` accidentally left in config or ENV var set
- **Prevention**: Verify `USE_FAKE_GOVBR` is only set in local `.env`, never in prod env
- **Test**: Assert `is_fake_mode=False` when config has production Gov.br URLs

### 3. **JWT Verification Silently Bypassed**

- **Symptom**: Unverified JWTs accepted without warning in production
- **Root cause**: No jwt_secret configured + no JWKS URL matching + unverified decode logged at WARNING only
- **Prevention**: Set appropriate jwt_secret or ensure JWKS URL matches known Gov.br issuer
- **Test**: Trigger unverified decode path, check logs contain warning

### 4. **Callback Returns Promise but Not Awaited (FastAPI)**

- **Symptom**: Callback result is `<coroutine>` object instead of user data
- **Root cause**: Callback is async but controller doesn't detect + await it
- **Prevention**: Controller already handles this with `asyncio.iscoroutine()` check
- **Test**: Pass async callback to FastAPI connector, verify it's awaited

### 5. **Flask Form Data vs Query Params**

- **Symptom**: Flask connector receives empty `code`, `state`
- **Root cause**: Code uses `request.args.get()` but client sent form data
- **Prevention**: Flask connector explicitly reads from query params (not body)
- **Test**: POST with code/state in query string, verify they're captured

### 6. **Fake Mode Path Extraction Breaks**

- **Symptom**: `/fake-govbr/authorize` endpoint not found on startup
- **Root cause**: URL path parsing fails for unusual URL formats
- **Prevention**: Test with various URL formats: `http://localhost:8000/fake-govbr/authorize`,
  `http://127.0.0.1:3000/auth/fake-govbr/authorize`
- **Test**: Init connector with edge case URLs, verify fake router path is correct

---

## Testing Strategy Deep Dive

### Unit Tests (core logic)

- **`test_config_and_errors.py`**: Pydantic validation, field stripping, env loading
- **`test_jwt_verification.py`**: JWT decode with different verification strategies (JWKS, jwt_secret, unverified)
- **`test_fake_govbr.py`**: FakeGovBrService token generation, user lookup, session tracking

### Integration Tests (framework + core)

- **`test_fastapi_auth.py`**: Full flow with FastAPI (authorize endpoint, callback endpoint)
- **`test_flask_auth.py`**: Full flow with Flask (query params, response format)
- **`test_django_auth.py`**: URL patterns, class-based views, response format

### Error Handling Tests

- **`test_error_handling.py`**: GovBrException vs GovBrAuthenticationError, HTTP status codes

### Fake Integration Tests

- **`test_fake_auto_integration.py`**: Fake mode detection, auto-registration of endpoints

### Test Pattern Used

```python
# Real environment setup
config = GovBrConfig(
        client_id="test_id",
        client_secret="test_secret",
        redirect_uri="http://localhost:8000/callback",
        cript_verifier_secret="<valid Fernet key>",
        ...
)

# Behavior verification
authorize = GovBrAuthorize(config)
result = authorize.build_authorize_url()
assert "url" in result
assert "state" in result["url"]
assert "code_challenge" in result["url"]
```

### Async Test Pattern

```python
@pytest.mark.asyncio
async def test_exchange_code_for_token():
    integration = GovBrIntegration(config)
    result = await integration.async_exchange_code_for_token(code, state)
    assert "id_token_decoded" in result
```

---

## When to Use Each Component

- **Use `GovBrConfig.from_env()`**: Simple deployments with `.env`
- **Use `GovBrConfig()` directly**: Complex initialization, multiple configs
- **Use `GovBrConnector.init_fastapi()`**: FastAPI, need automatic route setup
- **Use `GovBrAuthorize` + `GovBrIntegration` directly**: Custom frameworks, fine-grained control
- **Enable fake mode**: Local development, CI/CD, testing without Gov.br registration

---

## Integration Checklist for New Features

- [ ] Configuration validated in `GovBrConfig`
- [ ] Core logic in `govbr.py` (separate from frameworks)
- [ ] Controller adapts it for FastAPI/Flask/Django
- [ ] Fake mode auto-registers new endpoints if needed
- [ ] Tests added in appropriate `tests/test_*.py`
- [ ] Backward compatibility preserved (no breaking changes to public API)
- [ ] Type hints present where helpful
- [ ] Follows existing error handling pattern

---

## Backward Compatibility & Public API

### Public API Surface

```python
# Public exports from govbr_auth/__init__.py
GovBrConfig, GovBrAuthorize, GovBrIntegration, GovBrException, GovBrAuthenticationError,
GovBrConnector, FakeUserData, FakeGovBrService, AuthorizationRequest,
render_fake_login_page, process_fake_login, create_default_fake_users,
generate_cript_verifier_secret
```

### What's Considered a Breaking Change

- ❌ Removing or renaming public classes/methods
- ❌ Changing method signatures (adding required params without defaults)
- ❌ Changing HTTP status codes or response structure
- ❌ Removing `fake_users` or `fake_jwt_secret` parameters
- ❌ Changing exception hierarchy (existing except blocks should still work)

### Safe Changes

- ✅ Adding new optional parameters with sensible defaults
- ✅ Adding new public methods/classes
- ✅ Improving error messages (catch blocks won't break)
- ✅ Internal refactoring that preserves behavior
- ✅ Adding new test files or test cases

### Fake Mode Stability Guarantee

- Fake mode must remain backward compatible within major version
- Existing flows using fake mode should work without config changes
- New features in fake mode should not break existing integrations
- Session data structure (`FakeUserData`) is part of public API

---

## Performance & Concurrency Notes

### Async Concurrency

- **httpx.AsyncClient**: Thread-safe, can handle concurrent requests
- **Multiple simultaneous auth flows**: Each creates own GovBrIntegration instance (no shared state)
- **JWKS caching**: Single `_jwks_client` per GovBrIntegration instance (not shared)
- **Fernet encryption**: Thread-safe for encryption/decryption operations

### Session Data (Fake Mode)

- **In-memory storage**: `_SESSION_DATA` dict (module-level global)
- **Thread-safe concerns**: Concurrent fake mode usage in tests might need isolation
- **Restart persistence**: Data lost on server restart (acceptable for dev mode)
- **Scaling limitations**: Not suitable for multi-process deployments (use real Gov.br instead)

### Optimization Opportunities

- JWKS client caching could be shared across instances (current: per-instance)
- State parameter could be optimized for size if URL length becomes constraint
- Fake mode session cleanup could use TTL for production-like testing

---

## Debugging & Troubleshooting

### Enable Debug Logging

```python
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger('govbr_auth')
```

### Key Logging Points

- `GovBrConnector.__init__()`: Logs when fake mode detected
- `GovBrIntegration.jwt_payload_decode()`: Logs warning for unverified decode
- Error paths: Exception messages logged before re-raising

### Common Debug Scenarios

1. **"Invalid or missing code_verifier"**: Check `cript_verifier_secret` consistency
2. **JWT verification failed**: Check issuer URL matches JWKS endpoint registration
3. **Fake endpoints not found**: Verify URL parsing for `/fake-govbr/` prefix
4. **Callback not awaited**: Verify callback is properly async-compatible in FastAPI

---

## Development Environment Setup

### Required for Testing

```bash
pytest tests/
USE_FAKE_GOVBR=true uvicorn examples.example_simple_app:app --reload
```

### IDE Notes (PyCharm)

- Virtual environment auto-activated on terminal start
- Use `;` to chain commands in PowerShell (not `&&`)
- Black formatter integration available (install from settings)

### Code Formatting

```bash
black govbr_auth/ tests/
```

### Generating Valid Secrets

```python
from govbr_auth.utils import generate_cript_verifier_secret

secret = generate_cript_verifier_secret()  # Valid 44-char Fernet key
```

