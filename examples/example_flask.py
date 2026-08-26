"""Flask example that keeps the same consumer runtime across providers."""

from flask import Flask, jsonify

from examples.example_settings import runtime_settings
from govbr_auth.flask import GovBrAuth


def create_app() -> Flask:
    """Create the same Flask consumer runtime for either configured provider."""
    application = Flask(__name__)

    def authenticated(context, request):
        return jsonify({"authenticated": True})

    # The Flask consumer stays the same; fake mode changes only provider wiring.
    auth = GovBrAuth(on_success=authenticated, settings=runtime_settings())
    auth.register(application)
    return application
