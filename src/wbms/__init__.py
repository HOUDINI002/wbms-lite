"""WBMS-Lite: a small Wi-Fi billing and management system."""

from __future__ import annotations

import logging

from flask import Flask, jsonify
from flask.logging import default_handler

from wbms import db
from wbms.config import Settings, load_settings

__all__ = ["create_app", "register_blueprints", "configure_logging"]


def configure_logging(app: Flask) -> None:
    """Set the log level and format for the application logger.

    DEBUG when Flask runs in debug mode, INFO otherwise.
    """
    default_handler.setFormatter(
        logging.Formatter("[%(asctime)s] %(levelname)s in %(module)s: %(message)s")
    )
    app.logger.setLevel(logging.DEBUG if app.debug else logging.INFO)


def register_blueprints(app: Flask) -> None:
    """Attach every blueprint to ``app``.

    Empty for now. Later steps add one line per blueprint here, for example
    ``app.register_blueprint(portal_bp)``, so ``create_app`` never has to change.
    """


def create_app(settings: Settings | None = None) -> Flask:
    """Application factory.

    Args:
        settings: Ready-made settings, mostly for tests. When ``None`` they are
            loaded from the environment and the project's .env file.

    Returns:
        A configured Flask application.

    Raises:
        wbms.config.ConfigError: if the settings are missing or invalid.
    """
    if settings is None:
        settings = load_settings()

    app = Flask(
        __name__,
        instance_relative_config=True,
        template_folder="web/templates",
        static_folder="web/static",
    )
    app.config["SECRET_KEY"] = settings.SECRET_KEY
    app.extensions["wbms_settings"] = settings

    db.init_app(app)
    configure_logging(app)
    register_blueprints(app)

    @app.get("/health")
    def health():
        """Liveness probe used by monitoring and by the test suite."""
        return jsonify(status="ok")

    app.logger.info(
        "WBMS-Lite ready (payment=%s, router=%s)",
        settings.PAYMENT_GATEWAY,
        settings.ROUTER_ADAPTER,
    )

    from wbms.web.api_packages import bp as api_packages_bp
    from wbms.web.portal import bp as portal_bp

    app.register_blueprint(api_packages_bp)
    app.register_blueprint(portal_bp)

    return app
