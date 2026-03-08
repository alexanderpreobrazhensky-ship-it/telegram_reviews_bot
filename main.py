import logging

from services.client_bot_service.app.main import main as service_main


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.info("LIRA client-bot starting (root main.py)")
    service_main()
