"""Explicit Django demo routes and request-local wrappers for owned URL patterns."""

from functools import wraps

from django.http import HttpResponse, JsonResponse
from django.urls import path
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from govbr_auth.fake.debug.controller import DEBUG_PATH, SAFE_HEADERS, DebugController
from govbr_auth.fake.debug.presentation import render_debug_page, page_headers


def with_debug_patterns(patterns, application):
    controller = DebugController(application)

    def decorate(view):
        @wraps(view)
        def observed(request, *args, **kwargs):
            with controller.observe(
                request.method,
                request.path,
                request.META.get("QUERY_STRING", ""),
                request.headers.items(),
                request.COOKIES,
            ) as capture:
                response = view(request, *args, **kwargs)
                if capture is not None:
                    headers = list(response.headers.items()) + [
                        ("Set-Cookie", value.OutputString())
                        for value in response.cookies.values()
                    ]
                    capture.finish(response.status_code, headers)
                return response

        return observed

    for pattern in patterns:
        pattern.callback = decorate(pattern.callback)

    @require_http_methods(["GET"])
    def debug_page(request):
        page = render_debug_page(controller.login_path)
        return HttpResponse(page, headers=page_headers(page))

    @csrf_exempt
    @require_http_methods(["GET", "POST", "DELETE"])
    def trace_endpoint(request):
        reply = controller.manage(request.method, request.headers, request.COOKIES)
        response = (
            HttpResponse(status=204, headers=SAFE_HEADERS)
            if reply.payload is None
            else JsonResponse(reply.payload, status=reply.status, headers=SAFE_HEADERS)
        )
        if reply.cookie is not None:
            controller.set_trace_cookie(response, reply.cookie)
        return response

    return patterns + [
        path(DEBUG_PATH.lstrip("/"), debug_page, name="govbr-demo-debug"),
        path(
            (DEBUG_PATH + "/trace").lstrip("/"), trace_endpoint, name="govbr-demo-trace"
        ),
    ]
