from config import config

print("Тестирование конфигурации...")
print(f"Админ ID: {config.ADMIN_ID}")
print(f"Путь к БД: {config.get_database_path()}")
print(f"Кошелек: {config.YOOMONEY_WALLET}")

# Проверка настроек производительности
print(f"\nНастройки производительности:")
print(f"Макс. соединений: {config.MAX_CONNECTIONS}")
print(f"Воркеров: {config.WORKERS}")
print(f"Лимит сообщений: {config.MESSAGE_RATE_LIMIT}/мин")

# Полная информация
info = get_bot_info()
print(f"\nПолная информация о боте:")
for key, value in info.items():
    print(f"{key}: {value}")