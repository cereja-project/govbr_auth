"""Independent browser cookie jars for native adapter integration tests."""

from contextlib import ExitStack, contextmanager
from importlib import import_module
from types import ModuleType
from urllib.parse import urlsplit

import httpx


@contextmanager
def browser_application(framework, settings, *, clock, runtime=None):
    """Mount an adapter and create independent clients without mocking its core."""
    with ExitStack() as stack:
        received = []

        def success(context, request=None):
            received.append(context.user.sub)
            payload = {"authenticated": context.user.sub}
            if framework == "django":
                from django.http import JsonResponse

                return JsonResponse(payload)
            if framework == "flask":
                return payload
            from fastapi.responses import JSONResponse

            return JSONResponse(payload)

        async def async_success(context):
            return success(context)

        kwargs = {"runtime": runtime} if runtime is not None else {"settings": settings}
        auth = import_module(f"govbr_auth.{framework}").GovBrAuth(
            **kwargs,
            on_success=async_success if framework == "fastapi" else success,
            clock=clock,
        )
        origin = str(settings.oauth.redirect_uri).rsplit("/", 1)[0]
        origin = f"{urlsplit(origin).scheme}://{urlsplit(origin).netloc}"
        if framework == "django":
            import django
            from django.conf import settings as django_settings
            from django.test import Client, override_settings
            from django.urls import clear_url_caches

            if not django_settings.configured:
                django_settings.configure(SECRET_KEY="test-only")
            django.setup()
            urls = ModuleType("browser_binding_test_urls")
            urls.urlpatterns = auth.urlpatterns
            stack.enter_context(
                override_settings(ROOT_URLCONF=urls, ALLOWED_HOSTS=["*"], MIDDLEWARE=[])
            )
            clear_url_caches()
            stack.callback(clear_url_caches)
            stack.callback(auth.close)

            def browser():
                client = Client()

                def send(path, *, method="GET", data=None):
                    response = getattr(client, method.lower())(
                        path, data=data or {}, secure=origin.startswith("https:")
                    )
                    headers = list(response.headers.items()) + [
                        ("Set-Cookie", value.OutputString())
                        for value in response.cookies.values()
                    ]
                    return httpx.Response(
                        response.status_code, headers=headers, content=response.content
                    )

                return send

        elif framework == "flask":
            from flask import Flask

            app = Flask(__name__)
            app.config["TESTING"] = True
            auth.register(app)
            stack.callback(auth.close)

            def browser():
                client = app.test_client()

                def send(path, *, method="GET", data=None):
                    response = client.open(
                        path, method=method, data=data, base_url=origin
                    )
                    return httpx.Response(
                        response.status_code,
                        headers=list(response.headers),
                        content=response.data,
                    )

                return send

        else:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient

            app = FastAPI()
            app.include_router(auth.router)

            def browser():
                client = stack.enter_context(TestClient(app, base_url=origin))

                def send(path, *, method="GET", data=None):
                    return client.request(
                        method, path, data=data, follow_redirects=False
                    )

                return send

        yield auth, browser, received
