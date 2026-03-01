from __future__ import annotations

import logging

from flask import Flask

from .config import ReviewsConfig

logger = logging.getLogger("reviews_bot_service")


def build_app():
    cfg = ReviewsConfig.from_env()
    app = Flask(__name__)

    @app.get("/service-health")
    @app.get("/health")
    def reviews_health():
        return {
            "status": "ok",
            "service": "reviews_bot_service",
            "mode": cfg.mode,
        }

    return app, cfg


def main() -> None:
    app, cfg = build_app()
    logger.info("reviews_bot_service startup: mode=%s port=%s token_source=REVIEWS_TELEGRAM_BOT_TOKEN", cfg.mode, cfg.port)
    app.run(host=cfg.host, port=cfg.port)


if __name__ == "__main__":
    main()
