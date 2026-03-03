import logging

from services.client_bot_service.app.config import ClientBotConfig
from services.client_bot_service.app.main import main as client_main


if __name__ == "__main__":
    cfg = ClientBotConfig.from_env()
    _, token_source = ClientBotConfig.resolve_token()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("entrypoint").info(
        "starting effective_bot=client mode=%s port=%s token_source=%s public_base_url=%s webhook_url=%s",
        cfg.mode,
        cfg.port,
        token_source,
        cfg.public_base_url or "-",
        "set" if cfg.webhook_url else "-",
    )
    client_main()
