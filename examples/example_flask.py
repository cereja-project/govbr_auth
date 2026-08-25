"""Flask consumer using the synchronous govbr-auth adapter."""

from flask import Flask, jsonify

from examples.example_settings import runtime_settings
from govbr_auth.flask import GovBrAuth


def create_app() -> Flask:
    """Create a Flask application for the official or selected fake provider."""
    application = Flask(__name__)

    def authenticated(context, request):
        return jsonify({"authenticated": True})

    auth = GovBrAuth(on_success=authenticated, settings=runtime_settings())
    auth.register(application)
    return application
