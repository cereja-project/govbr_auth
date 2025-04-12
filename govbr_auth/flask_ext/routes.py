from flask import Blueprint, request, jsonify
from govbr_auth.core.config import GovBrConfig
from govbr_auth.core.govbr import GovBrAuthorize, GovBrIntegration
import asyncio


def get_blueprint(config: GovBrConfig):
    bp = Blueprint('govbr_auth', __name__, url_prefix=f"/{config.prefix}")

    @bp.route(f'/{config.authorize_endpoint}')
    def get_authorize_url():
        return jsonify(GovBrAuthorize(config).build_authorize_url())

    @bp.route(f'/{config.authenticate_endpoint}')
    def callback():
        code = request.args.get('code')
        state = request.args.get('state')
        result = asyncio.run(GovBrIntegration(config).async_exchange_code_for_token(code, state))
        return jsonify(result)

    return bp
