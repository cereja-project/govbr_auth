"""Flask consumer using the synchronous govbr-auth adapter."""

from flask import Flask, jsonify

from govbr_auth.flask import GovBrAuth


def create_app() -> Flask:
    """Create a Flask application for the official or selected fake provider."""
    application = Flask(__name__)

    def authenticated(context, request):
        return jsonify({"authenticated": True, "subject": context.user.subject})

    auth = GovBrAuth(on_success=authenticated)
    auth.register(application)
    return application
