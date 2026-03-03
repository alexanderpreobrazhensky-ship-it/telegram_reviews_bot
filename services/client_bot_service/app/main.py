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
            "service": "client-bot",
            "mode": cfg.mode,
            "token_source": app.config.get("CLIENT_TOKEN_SOURCE", "unknown"),
            "port": cfg.port,
        }

    return app, cfg


def main() -> None:
    app, cfg = build_app()
    _, token_source = ClientBotConfig.resolve_token()
    configure_telegram(cfg.token)
    storage_mode = "db" if cfg.database_url else "files"
    logger.info(
        "client_bot_service startup effective_runtime=node_bootstrap python_entrypoint=main.py mode=%s webhook_url=%s token_source=%s port=%s host=%s storage_mode=%s webapp_url=%s",
        cfg.mode,
        mask_webhook_url(cfg.webhook_url),
        token_source,
        cfg.port,
        cfg.host,
        storage_mode,
        cfg.webapp_url or "-",
    )
    if cfg.mode == "webhook":
        logger.info("mode=webhook")
        _, source = ClientBotConfig.resolve_public_base_url_with_source()
        logger.info("webhook_base_source=%s", source)
        if not cfg.webhook_url:
            logger.warning("webhook mode requested but WEBHOOK_URL/PUBLIC_BASE_URL/DOMAIN is missing or invalid; falling back to polling")
            delete_webhook(cfg.token, logger, drop_pending_updates=True)
            start_polling_background()
        else:
            logger.info("webhook_url=%s", mask_webhook_url(cfg.webhook_url))
            delete_webhook(cfg.token, logger, drop_pending_updates=True)
            logger.info("deleteWebhook ok")
            set_webhook(cfg.token, logger, cfg.webhook_url)
            logger.info("setWebhook ok")
    else:
        logger.info("mode=polling")
        delete_webhook(cfg.token, logger, drop_pending_updates=True)
        start_polling_background()
    app.run(host=cfg.host, port=cfg.port)


if __name__ == "__main__":
    main()
