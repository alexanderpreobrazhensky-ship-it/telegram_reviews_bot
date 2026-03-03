import logging

from services.client_bot_service.app.main import main as client_main


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("entrypoint").info("client-bot starting (root main.py)")
    client_main()
