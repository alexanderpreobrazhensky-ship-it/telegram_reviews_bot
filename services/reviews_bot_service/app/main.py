from __future__ import annotations

import main as legacy_reviews

from .config import ReviewsConfig


def build_app():
    cfg = ReviewsConfig.from_env()
    app = legacy_reviews.app

    if "reviews_service_health" not in app.view_functions:
        app.add_url_rule(
            "/service-health",
            endpoint="reviews_service_health",
            view_func=lambda: {
                "ok": True,
                "service": "reviews_bot_service",
                "ai_engine": getattr(legacy_reviews, "AI_ENGINE", "unknown"),
            },
            methods=["GET"],
        )

    return app, cfg


def main() -> None:
    app, cfg = build_app()
    app.run(host=cfg.host, port=cfg.port)


if __name__ == "__main__":
    main()
