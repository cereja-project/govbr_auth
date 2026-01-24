"""
Exemplo SIMPLIFICADO de aplicação FastAPI com Gov.br Auth.

Os endpoints fake são registrados AUTOMATICAMENTE pelo GovBrConnector
quando detecta URLs locais na configuração. Não é necessário código adicional!

Execute:
    USE_FAKE_GOVBR=true uvicorn example_simple_app:app --reload
"""

import os

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from govbr_auth import GovBrConfig, GovBrConnector, create_default_fake_users

# Detectar modo (fake ou real)
USE_FAKE = os.getenv("USE_FAKE_GOVBR", "true").lower() == "true"

# Configurar URLs
if USE_FAKE:
    print("🧪 Modo FAKE - Endpoints fake serão criados automaticamente!")
    config = GovBrConfig(
        client_id="fake-client-id",
        client_secret="fake-client-secret",
        redirect_uri="http://localhost:8000/auth/govbr/callback",
        cript_verifier_secret="Vvd9H5VC2Aqk-dwFOJX6MvQTuZZARmb37y7un9wkj0c=",
        # URLs locais ativam automaticamente o modo fake
        auth_url="http://localhost:8000/fake-govbr/authorize",
        token_url="http://localhost:8000/fake-govbr/token"
    )
else:
    config = GovBrConfig(
        client_id=os.getenv("GOVBR_CLIENT_ID"),
        client_secret=os.getenv("GOVBR_CLIENT_SECRET"),
        redirect_uri=os.getenv("GOVBR_REDIRECT_URI"),
        cript_verifier_secret=os.getenv("CRIPT_VERIFIER_SECRET"),
        auth_url="https://sso.staging.acesso.gov.br/authorize",
        token_url="https://sso.staging.acesso.gov.br/token"
    )

app = FastAPI(title="Exemplo Simplificado - Gov.br Auth")


# Callback de sucesso
def handle_success(data: dict, request: Request):
    user = data["id_token_decoded"]
    return HTMLResponse(f"""
        <!DOCTYPE html>
        <html>
        <head><title>Login Bem-sucedido</title></head>
        <body style="font-family: Arial; max-width: 600px; margin: 50px auto; text-align: center;">
            <h1>✅ Autenticado com Sucesso!</h1>
            <div style="background: #f0f0f0; padding: 20px; border-radius: 8px; margin: 20px 0;">
                <p><strong>Nome:</strong> {user.get('name')}</p>
                <p><strong>CPF:</strong> {user.get('sub') or user.get('cpf')}</p>
                <p><strong>E-mail:</strong> {user.get('email')}</p>
            </div>
            <a href="/" style="color: #1351b4;">← Voltar ao Início</a>
        </body>
        </html>
    """)


# Inicializar connector
# O fake_users é opcional - se não informar, usa usuários padrão
connector = GovBrConnector(
    config=config,
    on_auth_success=handle_success,
    fake_users=create_default_fake_users() if USE_FAKE else None
)

# Registrar rotas - endpoints fake são adicionados automaticamente!
connector.init_fastapi(app)


@app.get("/", response_class=HTMLResponse)
async def home():
    """Página inicial"""
    modo = "FAKE (Dev)" if USE_FAKE else "REAL (Prod)"

    users_info = ""
    if USE_FAKE and connector.fake_service:
        users_info = """
        <div style="background: #fff3cd; padding: 15px; border-radius: 8px; margin: 20px 0;">
            <h3>👥 Usuários de Teste</h3>
            <p>Use qualquer CPF abaixo (senha = próprio CPF):</p>
            <ul style="list-style: none; padding: 0;">
                <li>📋 CPF: <code>12345678901</code> - João da Silva</li>
                <li>📋 CPF: <code>98765432100</code> - Maria Oliveira</li>
                <li>📋 CPF: <code>11122233344</code> - José Santos</li>
            </ul>
            <p><small><a href="/fake-govbr/users">Ver lista completa (JSON)</a></small></p>
        </div>
        """

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Gov.br Auth - Exemplo Simplificado</title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                max-width: 800px;
                margin: 50px auto;
                padding: 20px;
            }}
            .card {{
                border: 1px solid #ddd;
                border-radius: 8px;
                padding: 20px;
                margin: 20px 0;
                background: #f9f9f9;
            }}
            .btn {{
                display: inline-block;
                padding: 12px 24px;
                background: #1351b4;
                color: white;
                text-decoration: none;
                border-radius: 4px;
                font-weight: bold;
            }}
            .btn:hover {{
                background: #0c3f8d;
            }}
            .badge {{
                display: inline-block;
                padding: 4px 8px;
                background: {"#28a745" if USE_FAKE else "#1351b4"};
                color: white;
                border-radius: 4px;
                font-size: 12px;
                font-weight: bold;
            }}
        </style>
    </head>
    <body>
        <h1>🇧🇷 Gov.br Auth</h1>
        <p>Exemplo simplificado de integração</p>
        
        <div class="card">
            <h2>Modo Atual: <span class="badge">{modo}</span></h2>
            <p>{'🧪 Usando simulador fake - perfeito para desenvolvimento!' if USE_FAKE else '🌐 Usando Gov.br real'}</p>
        </div>
        
        <div class="card">
            <h2>Fazer Login</h2>
            <p>Clique no botão abaixo para autenticar:</p>
            <a href="/auth/govbr/authorize" class="btn">🔐 Entrar com Gov.br</a>
        </div>
        
        {users_info}
        
        <div class="card">
            <h3>📖 Como Funciona</h3>
            <ol>
                <li>Clique em "Entrar com Gov.br"</li>
                <li>{'Faça login com um dos CPFs de teste' if USE_FAKE else 'Será redirecionado para o Gov.br real'}</li>
                <li>Após autenticação, veja seus dados na tela de sucesso</li>
            </ol>
            {'<p><strong>💡 Dica:</strong> Os endpoints fake são criados automaticamente pelo GovBrConnector!</p>' if USE_FAKE else ''}
        </div>
        
        <div class="card">
            <h3>🔧 Documentação</h3>
            <ul>
                <li><a href="/docs">API Docs (Swagger)</a></li>
                <li><a href="/redoc">API Docs (ReDoc)</a></li>
                {'<li><a href="/fake-govbr/users">Lista de Usuários Fake (JSON)</a></li>' if USE_FAKE else ''}
            </ul>
        </div>
    </body>
    </html>
    """


@app.get("/health")
async def health():
    """Health check"""
    return {
        "status": "ok",
        "modo": "fake" if USE_FAKE else "real",
        "fake_service_ativo": connector.fake_service is not None,
        "endpoints_fake_registrados": connector.is_fake_mode
    }

@app.get("/auth/govbr/callback")
async def auth_callback(request: Request):
    """Callback de autenticação Gov.br"""
    # requisição para http post para /auth/govbr/authenticate
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8000/auth/govbr/authenticate",
            json=dict(request.query_params.items())
        )
    return HTMLResponse(content=response.text, status_code=response.status_code)

if __name__ == "__main__":
    import uvicorn

    print("\n" + "="*70)
    print("🚀 Gov.br Auth - Exemplo Simplificado")
    print("="*70)
    print(f"Modo: {'🧪 FAKE' if USE_FAKE else '🌐 REAL'}")
    print(f"URL: http://localhost:8000")

    if USE_FAKE and connector.fake_service:
        print(f"\n✨ Endpoints fake registrados automaticamente:")
        print(f"   • GET  /fake-govbr/authorize (página de login)")
        print(f"   • POST /fake-govbr/login (processar login)")
        print(f"   • POST /fake-govbr/token (trocar code por token)")
        print(f"   • GET  /fake-govbr/users (listar usuários)")
        print(f"\n📝 {len(connector.fake_service.users)} usuários disponíveis")

    print("="*70 + "\n")

    uvicorn.run(app, host="0.0.0.0", port=8000)

