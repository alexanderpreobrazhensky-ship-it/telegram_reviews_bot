from __future__ import annotations

from bots.client_bot.main import (
    configure_telegram,
    create_flask_app,
    delete_webhook,
    mask_webhook_url,
    set_webhook,
    start_polling_background,
)

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
    app, cfg = build_app()
    _, token_source = ClientBotConfig.resolve_token()
    configure_telegram(cfg.token)
    storage_mode = "db" if cfg.database_url else "files"
    logger.info(
        "client_bot_service startup effective_bot=client mode=%s token_source=%s public_base_url=%s webhook_url=%s port=%s storage_mode=%s webapp_url=%s",
        cfg.mode,
        token_source,
        cfg.public_base_url or "-",
        mask_webhook_url(cfg.webhook_url),
        cfg.port,
        storage_mode,
        cfg.webapp_url or "-",
    )
    if cfg.mode == "webhook":
        delete_webhook(cfg.token, logger, drop_pending_updates=True)
        if cfg.webhook_url:
            set_webhook(cfg.token, logger, cfg.webhook_url)
    else:
        start_polling_background()
        delete_webhook(cfg.token, logger, drop_pending_updates=True)
    app.run(host=cfg.host, port=cfg.port)


if __name__ == "__main__":
    main()
