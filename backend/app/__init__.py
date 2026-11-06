from __future__ import annotations

from flask import Flask, request
from werkzeug.exceptions import HTTPException

from app.api.routes import create_api_blueprint
from app.core.config import load_settings
from app.db.base import create_all_tables, init_engine


def create_app() -> Flask:
    settings = load_settings()

    app = Flask(__name__)
    app.config.update(
        FLASK_ENV=settings.flask_env,
        FLASK_HOST=settings.flask_host,
        FLASK_PORT=settings.flask_port,
        API_PREFIX=settings.api_prefix,
        MAX_CONTENT_LENGTH=16 * 1024,
    )

    allowed_origins = set(settings.cors_origins)
    if "*" in allowed_origins:
        raise ValueError("CORS_ORIGINS must list explicit trusted origins")

    @app.after_request
    def add_cors_headers(response):
        origin = request.headers.get("Origin")
        if origin and origin in allowed_origins:
            response.headers["Access-Control-Allow-Origin"] = origin
        response.vary.add("Origin")
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        return response

    @app.errorhandler(HTTPException)
    def http_error(error):
        return {"error": error.name}, error.code

    @app.errorhandler(Exception)
    def internal_error(error):
        # Exception messages can contain SQL parameters or credentials.
        app.logger.error("Request failed (%s)", type(error).__name__)
        return {"error": "Internal server error"}, 500

    @app.route(f"{settings.api_prefix}", methods=["OPTIONS"])
    @app.route(f"{settings.api_prefix}/<path:_path>", methods=["OPTIONS"])
    def preflight(_path: str = ""):
        return "", 204

    init_engine(settings)
    create_all_tables()

    app.extensions["settings"] = settings

    api_blueprint = create_api_blueprint()
    app.register_blueprint(api_blueprint, url_prefix=settings.api_prefix)

    return app
