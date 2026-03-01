from __future__ import annotations

import importlib
import logging
import os

from .config import ReviewsConfig

logger = logging.getLogger("reviews_bot_service")


def build_app():
    cfg = ReviewsConfig.from_env()
    os.environ["TELEGRAM_BOT_TOKEN"] = cfg.token
    legacy_reviews = importlib.import_module("main")
    app = legacy_reviews.app

    if "reviews_service_health" not in app.view_functions:
        app.add_url_rule(
            "/service-health",
            endpoint="reviews_service_health",
            view_func=lambda: {
                "status": "ok",
                "service": "reviews_bot_service",
                "mode": cfg.mode,
            },
            methods=["GET"],
        )
    if "reviews_health" not in app.view_functions:
        app.add_url_rule(
            "/health",
            endpoint="reviews_health",
            view_func=lambda: {
                "status": "ok",
                "service": "reviews_bot_service",
                "mode": cfg.mode,
            },
            methods=["GET"],
        )

    return app, cfg


def main() -> None:
    app, cfg = build_app()
    logger.info("reviews_bot_service startup: mode=%s port=%s token_source=REVIEWS_TELEGRAM_BOT_TOKEN", cfg.mode, cfg.port)
    app.run(host=cfg.host, port=cfg.port)


if __name__ == "__main__":
    main()
