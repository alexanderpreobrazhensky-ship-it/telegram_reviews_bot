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
                "ok": True,
                "service": "reviews_bot_service",
                "ai_engine": getattr(legacy_reviews, "AI_ENGINE", "unknown"),
                "mode": cfg.mode,
            },
            methods=["GET"],
        )

    return app, cfg


def main() -> None:
    app, cfg = build_app()
    source = "REVIEWS_TELEGRAM_BOT_TOKEN" if os.getenv("REVIEWS_TELEGRAM_BOT_TOKEN") else "TELEGRAM_BOT_TOKEN"
    logger.info("reviews_bot_service startup: token_source=%s mode=%s", source, cfg.mode)
    app.run(host=cfg.host, port=cfg.port)


if __name__ == "__main__":
    main()
