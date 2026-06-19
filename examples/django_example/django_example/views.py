"""Views used by the govbr-auth Django example."""

from django.http import HttpRequest, HttpResponse, JsonResponse


def home(_request: HttpRequest) -> HttpResponse:
    """Render a small page that starts the Gov.br authorization flow."""
    return HttpResponse(
            """<!doctype html>
    <html lang="pt-BR">
    <head><meta charset="utf-8"><title>Gov.br Auth com Django</title></head>
    <body style="font-family: sans-serif; max-width: 42rem; margin: 3rem auto">
      <h1>Gov.br Auth com Django</h1>
      <p>O modo fake está habilitado por padrão para desenvolvimento local.</p>
      <button id="login" type="button">Entrar com Gov.br</button>
      <p><a href="/fake-govbr/users">Consultar usuários fake</a></p>
      <script>
        document.querySelector("#login").addEventListener("click", async () => {
          const response = await fetch("/auth/govbr/authorize");
          const payload = await response.json();
          if (!response.ok || !payload.url) {
            alert(payload.error || "Não foi possível iniciar a autenticação.");
            return;
          }
          window.location.assign(payload.url);
        });
      </script>
    </body>
    </html>"""
    )


def handle_auth_success(
    data: dict[str, object], _request: HttpRequest
) -> JsonResponse:
    """Return selected identity claims after a successful authentication."""
    identity_data = data.get("id_token_decoded", {})
    identity = identity_data if isinstance(identity_data, dict) else {}
    return JsonResponse(
            {
                "message": "Usuário autenticado com sucesso.",
                "name":    identity.get("name"),
                "cpf":     identity.get("sub") or identity.get("cpf"),
                "email":   identity.get("email"),
            }
    )
