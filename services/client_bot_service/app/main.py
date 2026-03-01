from __future__ import annotations

from bots.client_bot.main import create_flask_app, start_polling_background

from .config import ClientBotConfig
from .utils.logger import get_logger


logger = get_logger()


def build_app():
    cfg = ClientBotConfig.from_env()
    token, token_source = ClientBotConfig.resolve_token()
    app = create_flask_app(token, logger)
    app.config["CLIENT_TOKEN_SOURCE"] = token_source

    @app.get("/service-health")
    @app.get("/health")
    def health():
        return {
            "status": "ok",
            "service": "client_bot_service",
            "mode": cfg.mode,
            "token_source": app.config.get("CLIENT_TOKEN_SOURCE", "unknown"),
        }

    return app, cfg


def main() -> None:
    import os
    from bots.client_bot.main import resolve_webapp_public_url

    app, cfg = build_app()
    _, token_source = ClientBotConfig.resolve_token()
    logger.info(
        "client_bot_service startup: mode=%s domain=%s webapp_url=%s port=%s token_source=%s",
        cfg.mode,
        os.getenv("DOMAIN", "").strip() or "-",
        resolve_webapp_public_url() or "-",
        cfg.port,
        token_source,
    )
    if cfg.mode == "polling":
        start_polling_background()
    app.run(host=cfg.host, port=cfg.port)


if __name__ == "__main__":
    main()
