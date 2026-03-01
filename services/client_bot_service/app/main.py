from __future__ import annotations

from bots.client_bot.main import create_flask_app, start_polling_background

from .config import ClientBotConfig
from .utils.logger import get_logger


logger = get_logger()


def build_app():
    cfg = ClientBotConfig.from_env()
    app = create_flask_app(cfg.token, logger)

    @app.get("/service-health")
    def health():
        return {
            "ok": True,
            "service": "client_bot_service",
            "mode": cfg.mode,
        }

    return app, cfg


def main() -> None:
    app, cfg = build_app()
    if cfg.mode == "polling":
        start_polling_background()
    app.run(host=cfg.host, port=cfg.port)


if __name__ == "__main__":
    main()
