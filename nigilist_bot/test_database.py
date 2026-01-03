import asyncio
import sys
import os

# Добавляем текущую директорию в путь для импорта
sys.path.append(os.path.dirname(os.path.abspath(__file__)))


async def main():
    print("🧪 Запуск теста базы данных...")

    try:
        # Импортируем и тестируем базу данных
        from database_async import test_database
        await test_database()
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())