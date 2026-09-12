"""Local Flask blueprint instrumentation without application-wide request hooks."""

from functools import wraps

from flask import Response, jsonify, make_response, request

from govbr_auth.fake.debug.controller import DEBUG_PATH, SAFE_HEADERS, DebugController
from govbr_auth.fake.debug.presentation import render_debug_page, page_headers


def install_debug(consumer_blueprint, provider_blueprint, application):
    controller = DebugController(application)

    def decorate(view):
        @wraps(view)
        def observed(*args, **kwargs):
            with controller.observe(
                request.method,
                request.path,
                request.query_string.decode("utf-8", errors="replace"),
                request.headers.items(),
                request.cookies,
            ) as capture:
                response = make_response(view(*args, **kwargs))
                if capture is not None:
                    capture.finish(response.status_code, list(response.headers))
                return response

        return observed

    @consumer_blueprint.get(DEBUG_PATH)
    def debug_page():
        page = render_debug_page(controller.login_path)
        return Response(page, mimetype="text/html", headers=page_headers(page))

    @consumer_blueprint.route(DEBUG_PATH + "/trace", methods=["GET", "POST", "DELETE"])
    def trace_endpoint():
        reply = controller.manage(request.method, request.headers, request.cookies)
        response = (
            make_response("", 204)
            if reply.payload is None
            else make_response(jsonify(reply.payload), reply.status)
        )
        response.headers.update(SAFE_HEADERS)
        if reply.cookie is not None:
            controller.set_trace_cookie(response, reply.cookie)
        return response

    def instrument(state):
        prefix = state.name + "."
        for endpoint, view in list(state.app.view_functions.items()):
            if endpoint.startswith(prefix):
                state.app.view_functions[endpoint] = decorate(view)

    consumer_blueprint.record(instrument)
    provider_blueprint.record(instrument)
