from fastapi import APIRouter, Query
from govbr_auth.core.config import GovBrConfig
from govbr_auth.core.govbr import GovBrAuthorize, GovBrIntegration


def get_router(config: GovBrConfig) -> APIRouter:
    router = APIRouter(prefix=f"/{config.prefix}", tags=["GovBR Auth"])

    @router.get(f"/{config.authorize_endpoint}")
    async def get_authorize_url():
        return GovBrAuthorize(config).build_authorize_url()

    @router.get(f"/{config.authenticate_endpoint}")
    async def govbr_callback(code: str = Query(...),
                             state: str = Query(...)):
        return await GovBrIntegration(config).async_exchange_code_for_token(code, state)

    return router
