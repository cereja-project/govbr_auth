from django.http import JsonResponse
from django.views import View
from govbr_auth.core.config import GovBrConfig
from govbr_auth.core.govbr import GovBrAuthorize, GovBrIntegration
import asyncio


config = GovBrConfig.from_env()


class GovBrUrlView(View):
    def get(self,
            request):
        return JsonResponse(GovBrAuthorize(config).build_authorize_url())


class GovBrCallbackView(View):
    def get(self,
            request):
        code = request.GET.get('code')
        state = request.GET.get('state')
        result = asyncio.run(GovBrIntegration(config).async_exchange_code_for_token(code, state))
        return JsonResponse(result)
