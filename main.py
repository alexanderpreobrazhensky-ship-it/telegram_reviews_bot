# Получаем URL проекта на Railway автоматически
RAILWAY_URL = os.getenv("RAILWAY_STATIC_URL")
if not RAILWAY_URL:
    RAILWAY_URL = os.getenv("RAILWAY_PUBLIC_DOMAIN")
    if not RAILWAY_URL:
        # Локальный запуск для теста
        import sys
        if "pytest" in sys.modules or "LOCAL" in os.environ:
            RAILWAY_URL = "http://localhost:8000"
        else:
            raise RuntimeError("Railway URL not found in environment variables")

if not RAILWAY_URL.startswith("http"):
    RAILWAY_URL = "https://" + RAILWAY_URL

WEBHOOK_URL = RAILWAY_URL + "/webhook"
logger.info(f"Webhook URL: {WEBHOOK_URL}")