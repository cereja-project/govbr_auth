"""Optional route instrumentation for the FastAPI demo, not global middleware."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.routing import APIRoute

from govbr_auth.fake.debug.controller import DEBUG_PATH, SAFE_HEADERS, DebugController
from govbr_auth.fake.debug.presentation import render_debug_page, page_headers


def observe_router(router: APIRouter, controller: DebugController) -> APIRouter:

    class ObservedRoute(APIRoute):
        def get_route_handler(self):
            original = super().get_route_handler()

            async def observed(request: Request):
                with controller.observe(
                    request.method,
                    request.url.path,
                    request.url.query,
                    request.headers.items(),
                    request.cookies,
                ) as capture:
                    response = await original(request)
                    if capture is not None:
                        capture.finish(
                            response.status_code,
                            [
                                (key.decode("latin-1"), value.decode("latin-1"))
                                for key, value in response.raw_headers
                            ],
                        )
                    return response

            return observed

    result = APIRouter(lifespan=router.lifespan_context)
    for route in router.routes:
        if not isinstance(route, APIRoute):
            result.routes.append(route)
            continue
        result.add_api_route(
            route.path,
            route.endpoint,
            response_model=route.response_model,
            status_code=route.status_code,
            tags=route.tags,
            dependencies=route.dependencies,
            summary=route.summary,
            description=route.description,
            response_description=route.response_description,
            responses=route.responses,
            deprecated=route.deprecated,
            methods=route.methods,
            operation_id=route.operation_id,
            response_model_include=route.response_model_include,
            response_model_exclude=route.response_model_exclude,
            response_model_by_alias=route.response_model_by_alias,
            response_model_exclude_unset=route.response_model_exclude_unset,
            response_model_exclude_defaults=route.response_model_exclude_defaults,
            response_model_exclude_none=route.response_model_exclude_none,
            include_in_schema=route.include_in_schema,
            response_class=route.response_class,
            name=route.name,
            callbacks=route.callbacks,
            openapi_extra=route.openapi_extra,
            route_class_override=ObservedRoute,
        )

    return result


def add_debug_routes(result: APIRouter, controller: DebugController) -> None:
    @result.get(DEBUG_PATH, include_in_schema=False)
    async def debug_page() -> HTMLResponse:
        page = render_debug_page(controller.login_path)
        return HTMLResponse(page, headers=page_headers(page))

    @result.api_route(
        DEBUG_PATH + "/trace",
        methods=["GET", "POST", "DELETE"],
        include_in_schema=False,
    )
    async def trace_endpoint(request: Request) -> Response:
        reply = controller.manage(request.method, request.headers, request.cookies)
        response = (
            Response(status_code=204, headers=SAFE_HEADERS)
            if reply.payload is None
            else JSONResponse(
                reply.payload, status_code=reply.status, headers=SAFE_HEADERS
            )
        )
        if reply.cookie is not None:
            controller.set_trace_cookie(response, reply.cookie)
        return response
