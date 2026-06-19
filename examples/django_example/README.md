# Exemplo Django

Este projeto mínimo demonstra o uso de `GovBrConnector` com Django. O modo Gov.br fake é habilitado por padrão, então nenhuma credencial externa é necessária.

A partir da raiz do repositório:

```bash
python -m pip install -r requirements-dev.txt
python examples/django_example/manage.py runserver
```

Abra <http://127.0.0.1:8000/> e selecione **Entrar com Gov.br**. No modo fake, use um dos CPFs listados como nome de usuário e senha.

Para usar o serviço real, defina `USE_FAKE_GOVBR=false` e configure `GOVBR_CLIENT_ID`, `GOVBR_CLIENT_SECRET`, `GOVBR_REDIRECT_URI` e `CRIPT_VERIFIER_SECRET`. O URI de redirecionamento registrado deve apontar para `http://127.0.0.1:8000/auth/govbr/authenticate` na execução local. As variáveis opcionais de endpoint estão documentadas no `.env.example` do repositório.
