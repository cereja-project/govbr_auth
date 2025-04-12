from django.http import JsonResponse
from django.views import View
from govbr_auth.core.govbr import GovBrAuthorize, GovBrIntegration
import asyncio


class GovBrUrlView(View):
    config = None

    def dispatch(self,
                 request,
                 *args,
                 **kwargs):
        self.config = kwargs.pop('config', None)
        return super().dispatch(request, *args, **kwargs)

    def get(self,
            request):
        return JsonResponse(GovBrAuthorize(self.config).build_authorize_url())


class GovBrCallbackView(View):
    config = None

    def dispatch(self,
                 request,
                 *args,
                 **kwargs):
        self.config = kwargs.pop('config', None)
        return super().dispatch(request, *args, **kwargs)

    def get(self,
            request):
        code = request.GET.get('code')
        state = request.GET.get('state')
        result = asyncio.run(GovBrIntegration(self.config).async_exchange_code_for_token(code, state))
        return JsonResponse(result)
