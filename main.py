def main():
    """Запуск бота"""
    print("🔄 Создаю приложение Telegram...")
    
    # Добавьте drop_pending_updates=True
    app = ApplicationBuilder()\
        .token(TELEGRAM_TOKEN)\
        .post_init(post_init)\
        .build()
    
    # ... остальной код ...
    
    # Замените эту строку:
    # app.run_polling()
    
    # На эту:
    app.run_polling(
        drop_pending_updates=True,  # Игнорировать старые обновления
        close_loop=False,
        stop_signals=None
    )
