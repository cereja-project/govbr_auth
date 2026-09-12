"""Opt-in demo request contexts and HTTPX hooks, isolated from OAuth core code."""

import hashlib
from collections.abc import Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from urllib.parse import parse_qs, urlsplit

import httpx

from govbr_auth.runtime_settings import GovBrProvider
from govbr_auth.fake.debug import redaction
from govbr_auth.fake.debug.trace import Trace, TraceStore

DEBUG_PATH = "/govbr-auth-demo/debug"
SAFE_HEADERS = {
    "Cache-Control": "no-store",
    "Pragma": "no-cache",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Resource-Policy": "same-origin",
    "X-Frame-Options": "DENY",
}
_CURRENT: ContextVar["Observation | None"] = ContextVar(
    "govbr_demo_observation", default=None
)


@dataclass
class ManagementReply:
    status: int
    payload: dict | None
    cookie: str | None = None


class DebugController:
    """Observe only the fake runtime owned/borrowed by one demo adapter."""

    def __init__(self, application) -> None:
        runtime = application.runtime
        if runtime.provider is not GovBrProvider.FAKE or runtime.fake is None:
            raise ValueError("debug tracing requires the fake provider")
        self.store = TraceStore()
        self.login_path = application.login_path
        self.callback_path = application.callback_path
        oauth = runtime.client.settings
        uri = urlsplit(str(oauth.redirect_uri))
        self.origin = f"{uri.scheme}://{uri.netloc}"
        self.secure = uri.scheme == "https"
        scope = hashlib.sha256(
            f"{oauth.client_id}\0{oauth.redirect_uri}".encode()
        ).hexdigest()[:16]
        self.cookie_name = (
            ("__Host-" if self.secure else "") + "govbr-demo-trace-" + scope
        )
        self.paths = {
            self.login_path: "prepare",
            self.callback_path: "callback",
            runtime.fake.prefix + "/authorize": "authorize",
            runtime.fake.prefix + "/login": "provider_login",
            runtime.fake.prefix + "/token": "token",
            runtime.fake.prefix + "/jwk": "jwks",
            runtime.fake.prefix + "/userinfo": "userinfo",
            runtime.fake.prefix + "/logout": "logout",
            "/": "home",
            "/govbr-auth-demo": "home",
        }
        if application.logout_path:
            self.paths[application.logout_path] = "logout"
        http = runtime._owned_http
        if http is not None:
            for name, hook in (
                ("request", record_http_request),
                ("response", record_http_response),
            ):
                if hook not in http.event_hooks[name]:
                    http.event_hooks[name].append(hook)

    def manage(
        self, method: str, headers: Mapping[str, str], cookies: Mapping[str, str]
    ) -> ManagementReply:
        incoming = {key.lower(): value for key, value in headers.items()}
        origin = incoming.get("origin")
        if incoming.get("x-govbr-demo") != "1" or (
            origin != self.origin and (method != "GET" or origin is not None)
        ):
            return ManagementReply(403, {"error": "demo_origin_required"})
        key = cookies.get(self.cookie_name, "")
        if method == "POST":
            key, trace = self.store.start(key)
            return ManagementReply(201, trace.snapshot(), key)
        if method == "DELETE":
            self.store.stop(key)
            return ManagementReply(204, None, "")
        trace = self.store.get(key)
        if trace is None:
            return ManagementReply(404, {"error": "demo_trace_expired"})
        return ManagementReply(200, trace.snapshot())

    def set_trace_cookie(self, response, value: str) -> None:
        response.set_cookie(
            self.cookie_name,
            value,
            httponly=True,
            secure=self.secure,
            samesite="strict",
            path="/",
            max_age=self.store.ttl if value else 0,
        )

    @contextmanager
    def observe(self, method: str, path: str, query: str, headers, cookies):
        trace = self.store.get(cookies.get(self.cookie_name, ""))
        phase = self.paths.get(path)
        if trace is None or trace.completed or phase is None or phase == "home":
            yield None
            return
        observation = Observation(self, trace, phase, method, path, query, headers)
        token = _CURRENT.set(observation)
        try:
            yield observation
        except Exception:
            observation.finish(None, [])
            raise
        finally:
            _CURRENT.reset(token)


class Observation:
    """A request-local handle; no request/response object is kept in the trace."""

    def __init__(
        self,
        controller,
        trace: Trace,
        phase: str,
        method: str,
        path: str,
        query: str,
        headers,
    ) -> None:
        self.controller, self.trace, self.phase = controller, trace, phase
        self.finished = False
        self.number = trace.append(
            phase,
            request={
                "method": method if method in {"GET", "POST", "HEAD"} else "OTHER",
                "path": path,
                "query": redaction.fields(
                    parse_qs(query[:16_384], keep_blank_values=True)
                ),
                "headers": redaction.headers(list(headers), controller.paths),
                "body": {"body": "[corpo do navegador não capturado]"},
            },
        )
        if phase == "callback":
            trace.finish(self.number)
            if self.number is not None:
                with trace.lock:
                    trace.events[self.number]["response"] = None

    def finish(self, status: int | None, headers) -> None:
        with self.trace.lock:
            if self.finished:
                return
            self.finished = True
            number = self.number
            if self.phase == "callback":
                number = self.trace.append("result")
                for event in self.trace.events:
                    if event["status"] == "running":
                        self.trace.finish(event["id"], status=None)
            self.trace.finish(
                number,
                status=status,
                headers=redaction.headers(list(headers), self.controller.paths),
            )
            if self.phase == "callback":
                self.trace.completed = True


async def record_http_request(request: httpx.Request) -> None:
    observation = _CURRENT.get()
    if observation is None:
        return
    phase = observation.controller.paths.get(request.url.path)
    if phase not in {"token", "jwks", "userinfo"}:
        return
    if observation.phase == "callback" and phase == "token":
        observation.trace.inferred("binding")
    if observation.phase == "callback" and phase == "userinfo":
        observation.trace.inferred("validation")
    number = observation.trace.append(
        phase,
        request={
            "method": request.method,
            "path": request.url.path,
            "query": redaction.fields(dict(request.url.params)),
            "headers": redaction.headers(
                list(request.headers.multi_items()), observation.controller.paths
            ),
            "body": redaction.body(
                request.content, request.headers.get("content-type", "")
            ),
        },
    )
    request.extensions["govbr_demo_event"] = number


async def record_http_response(response: httpx.Response) -> None:
    observation = _CURRENT.get()
    if observation is None or "govbr_demo_event" not in response.request.extensions:
        return
    await response.aread()
    observation.trace.finish(
        response.request.extensions["govbr_demo_event"],
        status=response.status_code,
        headers=redaction.headers(
            list(response.headers.multi_items()), observation.controller.paths
        ),
        body=redaction.body(response.content, response.headers.get("content-type", "")),
    )
