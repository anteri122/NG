import os
from dotenv import load_dotenv

print("🔍 Проверка .env файла...")
print(f"Текущая директория: {os.getcwd()}")

# Пробуем загрузить .env
load_dotenv()

# Проверяем переменные
bot_token = os.getenv("BOT_TOKEN")
admin_id = os.getenv("ADMIN_ID")
wallet = os.getenv("YOOMONEY_WALLET")

print(f"BOT_TOKEN: {'✅ Загружен' if bot_token else '❌ Не найден'}")
print(f"ADMIN_ID: {'✅ Загружен' if admin_id else '❌ Не найден'}")
print(f"YOOMONEY_WALLET: {'✅ Загружен' if wallet else '❌ Не найден'}")

if bot_token:
    print(f"Токен (первые 10 символов): {bot_token[:10]}...")
if wallet:
    print(f"Кошелек: {wallet}")