import os
import sys


class Config:
    # ============ ПОПЫТКА ЗАГРУЗКИ ИЗ .env ============
    try:
        from dotenv import load_dotenv
        load_dotenv()
        print("✅ .env файл загружен")
    except ImportError:
        print("⚠️ python-dotenv не установлен. Установите: pip install python-dotenv")
    except Exception as e:
        print(f"⚠️ Ошибка загрузки .env: {e}")

    # ============ ОСНОВНЫЕ НАСТРОЙКИ ============

    # Токен бота
    BOT_TOKEN = os.getenv("BOT_TOKEN", "8592076563:AAFnn33ARbPUO4Aw29Kq93UE7Gi_SpyZSSM")

    # Ваш Telegram ID
    ADMIN_ID = int(os.getenv("ADMIN_ID", "824840538"))

    # Кошелек ЮMoney
    YOOMONEY_WALLET = os.getenv("YOOMONEY_WALLET", "4100119434757045")

    # ============ ПРОИЗВОДИТЕЛЬНОСТЬ ============

    # Режим отладки
    DEBUG_MODE = True

    # Лимит сообщений
    MESSAGE_RATE_LIMIT = 30

    # ============ ПУТИ К ФАЙЛАМ ============

    DATABASE_PATH = "data/bot_database.db"
    LOG_FILE = "logs/bot.log"

    # ============ ПЛАТЕЖИ ============

    MIN_PAYMENT_AMOUNT = 10.0
    MAX_PAYMENT_AMOUNT = 50000.0

    # ============ МЕТОДЫ ДЛЯ ПУТЕЙ ============

    @staticmethod
    def get_database_path():
        """Возвращает путь к базе данных"""
        os.makedirs("data", exist_ok=True)
        return Config.DATABASE_PATH

    @staticmethod
    def get_logs_path():
        """Возвращает путь к логам"""
        os.makedirs("logs", exist_ok=True)
        return Config.LOG_FILE

    # ============ ПРОВЕРКА КОНФИГУРАЦИИ ============

    @classmethod
    def validate(cls):
        print("=" * 50)
        print("🤖 ПРОВЕРКА КОНФИГУРАЦИИ")
        print("=" * 50)

        # Проверяем токен
        if not cls.BOT_TOKEN or cls.BOT_TOKEN == "ваш_токен_бота":
            print("❌ ОШИБКА: Токен бота не настроен!")
            print("   Получите новый токен у @BotFather")
            return False

        print(f"✅ Токен бота: {cls.BOT_TOKEN[:10]}...")
        print(f"✅ Админ ID: {cls.ADMIN_ID}")
        print(f"✅ Кошелек: {cls.YOOMONEY_WALLET}")
        print(f"✅ Режим отладки: {'ВКЛ' if cls.DEBUG_MODE else 'ВЫКЛ'}")
        print(f"✅ База данных: {cls.get_database_path()}")
        print("=" * 50)
        return True


# Создаем объект конфигурации
config = Config()

# Проверяем при импорте
if not Config.validate():
    print("\n🚨 НЕОБХОДИМЫЕ ДЕЙСТВИЯ:")
    print("1. Получите новый токен у @BotFather командой /newbot")
    print("2. Обновите токен в коде выше (строка 18)")
    print("3. Или создайте файл .env с переменными")
    sys.exit(1)