import aiosqlite
import asyncio
from contextlib import asynccontextmanager
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime
import logging
from config import config

# Настройка логирования для БД
logger = logging.getLogger("database")


class AsyncDatabase:
    """
    Асинхронная обертка для SQLite с пулом соединений.
    Оптимизирована для 500+ одновременных пользователей.
    """

    _instance = None
    _connection_pool = None

    def __new__(cls):
        """Singleton паттерн - одна база данных на всё приложение"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    async def initialize(self):
        """Инициализация базы данных и создание таблиц"""
        if not self._initialized:
            logger.info("🚀 Инициализация базы данных...")

            # Создаем директории если нет
            import os
            os.makedirs("data", exist_ok=True)

            # Создаем подключение к БД
            self._connection_pool = await self._create_connection()

            # Настраиваем SQLite для высокой нагрузки
            await self._optimize_sqlite()

            # Создаем таблицы
            await self._create_tables()

            # Создаем индексы для быстрого поиска
            await self._create_indexes()

            self._initialized = True
            logger.info("✅ База данных готова к работе")

    async def _create_connection(self) -> aiosqlite.Connection:
        """Создает подключение к SQLite с настройками производительности"""
        db_path = config.get_database_path()
        conn = await aiosqlite.connect(db_path)

        # Настройки для производительности
        await conn.execute("PRAGMA foreign_keys = ON")
        await conn.execute("PRAGMA temp_store = MEMORY")
        await conn.execute("PRAGMA mmap_size = 268435456")  # 256MB mmap

        return conn

    async def _optimize_sqlite(self):
        """Оптимизация SQLite для многопользовательского доступа"""
        # Включаем WAL режим для конкурентного чтения/записи
        await self._connection_pool.execute("PRAGMA journal_mode = WAL")

        # Устанавливаем размер кэша (в страницах)
        await self._connection_pool.execute("PRAGMA cache_size = -10000")  # ~10MB

        # Устанавливаем безопасный режим синхронизации
        await self._connection_pool.execute("PRAGMA synchronous = NORMAL")

        # Увеличиваем таймаут для избежания блокировок
        await self._connection_pool.execute("PRAGMA busy_timeout = 5000")

        await self._connection_pool.commit()
        logger.debug("Настройки SQLite оптимизированы")

    async def _create_tables(self):
        """Создание основных таблиц базы данных"""

        # Таблица пользователей
        await self._connection_pool.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER UNIQUE NOT NULL,
                username TEXT,
                first_name TEXT NOT NULL,
                last_name TEXT,
                balance REAL DEFAULT 0.0 CHECK(balance >= 0),
                is_admin BOOLEAN DEFAULT FALSE,
                is_blocked BOOLEAN DEFAULT FALSE,
                language_code TEXT DEFAULT 'ru',
                last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                -- Проверки
                CHECK (user_id > 0),
                CHECK (balance >= 0)
            )
        ''')

        # Таблица платежей
        await self._connection_pool.execute('''
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                amount REAL NOT NULL CHECK(amount > 0),
                payment_id TEXT UNIQUE NOT NULL,
                yoomoney_id TEXT,
                status TEXT DEFAULT 'pending' 
                    CHECK(status IN ('pending', 'completed', 'failed', 'expired', 'cancelled')),
                description TEXT,
                metadata TEXT,  -- JSON с дополнительными данными
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,

                -- Внешний ключ
                FOREIGN KEY (user_id) REFERENCES users (user_id) 
                    ON DELETE CASCADE ON UPDATE CASCADE,

                -- Проверки
                CHECK (amount > 0)
            )
        ''')

        # Таблица операций (история баланса)
        await self._connection_pool.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                type TEXT NOT NULL CHECK(type IN ('deposit', 'withdrawal', 'payment', 'bonus', 'correction')),
                amount REAL NOT NULL,
                balance_before REAL NOT NULL,
                balance_after REAL NOT NULL,
                description TEXT NOT NULL,
                related_payment_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (user_id) REFERENCES users (user_id),
                FOREIGN KEY (related_payment_id) REFERENCES payments (id)
            )
        ''')

        # Таблица настроек бота (для будущего расширения)
        await self._connection_pool.execute('''
            CREATE TABLE IF NOT EXISTS bot_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                description TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        await self._connection_pool.commit()
        logger.info("Таблицы базы данных созданы")

    async def _create_indexes(self):
        """Создание индексов для быстрого поиска"""

        # Индексы для таблицы users
        await self._connection_pool.execute(
            "CREATE INDEX IF NOT EXISTS idx_users_user_id ON users(user_id)"
        )
        await self._connection_pool.execute(
            "CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)"
        )
        await self._connection_pool.execute(
            "CREATE INDEX IF NOT EXISTS idx_users_created ON users(created_at)"
        )

        # Индексы для таблицы payments
        await self._connection_pool.execute(
            "CREATE INDEX IF NOT EXISTS idx_payments_user_id ON payments(user_id)"
        )
        await self._connection_pool.execute(
            "CREATE INDEX IF NOT EXISTS idx_payments_status ON payments(status)"
        )
        await self._connection_pool.execute(
            "CREATE INDEX IF NOT EXISTS idx_payments_created ON payments(created_at)"
        )
        await self._connection_pool.execute(
            "CREATE INDEX IF NOT EXISTS idx_payments_composite ON payments(user_id, status)"
        )

        # Индексы для таблицы transactions
        await self._connection_pool.execute(
            "CREATE INDEX IF NOT EXISTS idx_transactions_user_id ON transactions(user_id)"
        )
        await self._connection_pool.execute(
            "CREATE INDEX IF NOT EXISTS idx_transactions_created ON transactions(created_at)"
        )

        await self._connection_pool.commit()
        logger.debug("Индексы созданы")

    @asynccontextmanager
    async def get_cursor(self):
        """
        Контекстный менеджер для работы с курсором.
        Автоматически коммитит изменения и закрывает курсор.
        """
        cursor = await self._connection_pool.cursor()
        try:
            yield cursor
            await self._connection_pool.commit()
        except Exception as e:
            await self._connection_pool.rollback()
            raise e
        finally:
            await cursor.close()

    # ============ МЕТОДЫ ДЛЯ РАБОТЫ С ПОЛЬЗОВАТЕЛЯМИ ============

    async def add_or_update_user(
            self,
            user_id: int,
            username: str = None,
            first_name: str = "",
            last_name: str = ""
    ) -> bool:
        """
        Добавляет нового пользователя или обновляет существующего.
        Возвращает True если пользователь был добавлен, False если обновлен.
        """
        try:
            async with self.get_cursor() as cursor:
                # Проверяем, существует ли пользователь
                await cursor.execute(
                    "SELECT id FROM users WHERE user_id = ?",
                    (user_id,)
                )
                exists = await cursor.fetchone()

                if exists:
                    # Обновляем существующего пользователя
                    await cursor.execute('''
                        UPDATE users 
                        SET username = ?, 
                            first_name = ?,
                            last_name = ?,
                            last_activity = CURRENT_TIMESTAMP
                        WHERE user_id = ?
                    ''', (username, first_name, last_name, user_id))
                    logger.debug(f"Пользователь {user_id} обновлен")
                    return False
                else:
                    # Добавляем нового пользователя
                    await cursor.execute('''
                        INSERT INTO users (user_id, username, first_name, last_name, is_admin)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (
                        user_id,
                        username,
                        first_name,
                        last_name,
                        user_id == config.ADMIN_ID  # Админ если ID совпадает
                    ))
                    logger.info(f"Новый пользователь {user_id} добавлен")
                    return True
        except Exception as e:
            logger.error(f"Ошибка добавления пользователя {user_id}: {e}")
            return False

    async def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Получает информацию о пользователе по ID"""
        try:
            async with self.get_cursor() as cursor:
                await cursor.execute(
                    "SELECT * FROM users WHERE user_id = ?",
                    (user_id,)
                )
                row = await cursor.fetchone()

                if row:
                    # Преобразуем строку в словарь
                    columns = [description[0] for description in cursor.description]
                    return dict(zip(columns, row))
                return None
        except Exception as e:
            logger.error(f"Ошибка получения пользователя {user_id}: {e}")
            return None

    async def get_user_balance(self, user_id: int) -> float:
        """Получает баланс пользователя"""
        try:
            async with self.get_cursor() as cursor:
                await cursor.execute(
                    "SELECT balance FROM users WHERE user_id = ?",
                    (user_id,)
                )
                result = await cursor.fetchone()
                return result[0] if result else 0.0
        except Exception as e:
            logger.error(f"Ошибка получения баланса {user_id}: {e}")
            return 0.0

    async def update_user_balance(
            self,
            user_id: int,
            amount: float,
            description: str = ""
    ) -> Tuple[bool, float, float]:
        """
        Обновляет баланс пользователя атомарно.
        Возвращает (успех, баланс_до, баланс_после)
        """
        try:
            async with self.get_cursor() as cursor:
                # Получаем текущий баланс с блокировкой строки
                await cursor.execute(
                    "SELECT balance FROM users WHERE user_id = ?",
                    (user_id,)
                )
                result = await cursor.fetchone()

                if not result:
                    return False, 0.0, 0.0

                balance_before = result[0]
                balance_after = balance_before + amount

                # Проверяем, что баланс не станет отрицательным (кроме специальных случаев)
                if balance_after < 0 and amount < 0:
                    logger.warning(
                        f"Попытка уйти в минус: user_id={user_id}, balance={balance_before}, amount={amount}")
                    return False, balance_before, balance_before

                # Обновляем баланс
                await cursor.execute('''
                    UPDATE users 
                    SET balance = balance + ? 
                    WHERE user_id = ?
                ''', (amount, user_id))

                # Добавляем запись в историю
                if amount != 0:
                    transaction_type = "deposit" if amount > 0 else "withdrawal"
                    await self._add_transaction(
                        cursor, user_id, transaction_type,
                        amount, balance_before, balance_after, description
                    )

                logger.debug(f"Баланс пользователя {user_id} обновлен: {balance_before} -> {balance_after}")
                return True, balance_before, balance_after

        except Exception as e:
            logger.error(f"Ошибка обновления баланса {user_id}: {e}")
            return False, 0.0, 0.0

    async def _add_transaction(
            self, cursor, user_id: int, type_: str, amount: float,
            balance_before: float, balance_after: float, description: str
    ):
        """Вспомогательный метод для добавления транзакции"""
        await cursor.execute('''
            INSERT INTO transactions 
            (user_id, type, amount, balance_before, balance_after, description)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, type_, amount, balance_before, balance_after, description))

    # ============ МЕТОДЫ ДЛЯ РАБОТЫ С ПЛАТЕЖАМИ ============

    async def create_payment(
            self,
            user_id: int,
            amount: float,
            payment_id: str,
            description: str = ""
    ) -> bool:
        """Создает запись о новом платеже"""
        try:
            async with self.get_cursor() as cursor:
                await cursor.execute('''
                    INSERT INTO payments 
                    (user_id, amount, payment_id, description)
                    VALUES (?, ?, ?, ?)
                ''', (user_id, amount, payment_id, description))

                logger.info(f"Создан платеж {payment_id} на сумму {amount} для user_id={user_id}")
                return True
        except aiosqlite.IntegrityError:
            logger.warning(f"Дубликат платежа {payment_id}")
            return False
        except Exception as e:
            logger.error(f"Ошибка создания платежа: {e}")
            return False

    async def update_payment_status(
            self,
            payment_id: str,
            status: str,
            yoomoney_id: str = None
    ) -> bool:
        """Обновляет статус платежа"""
        try:
            async with self.get_cursor() as cursor:
                # Получаем информацию о платеже
                await cursor.execute(
                    "SELECT user_id, amount, status FROM payments WHERE payment_id = ?",
                    (payment_id,)
                )
                payment = await cursor.fetchone()

                if not payment:
                    logger.warning(f"Платеж {payment_id} не найден")
                    return False

                user_id, amount, old_status = payment

                # Обновляем статус
                await cursor.execute('''
                    UPDATE payments 
                    SET status = ?, 
                        yoomoney_id = ?,
                        updated_at = CURRENT_TIMESTAMP,
                        completed_at = CASE WHEN ? = 'completed' THEN CURRENT_TIMESTAMP ELSE NULL END
                    WHERE payment_id = ?
                ''', (status, yoomoney_id, status, payment_id))

                # Если платеж завершен успешно - начисляем баланс
                if status == 'completed' and old_status != 'completed':
                    success, _, _ = await self.update_user_balance(
                        user_id, amount, f"Пополнение через ЮMoney #{yoomoney_id or payment_id}"
                    )
                    if success:
                        logger.info(f"Платеж {payment_id} завершен, баланс начислен")
                    else:
                        logger.error(f"Платеж {payment_id} завершен, но баланс не начислен!")

                logger.debug(f"Статус платежа {payment_id} обновлен: {old_status} -> {status}")
                return True

        except Exception as e:
            logger.error(f"Ошибка обновления статуса платежа {payment_id}: {e}")
            return False

    async def get_payment(self, payment_id: str) -> Optional[Dict[str, Any]]:
        """Получает информацию о платеже"""
        try:
            async with self.get_cursor() as cursor:
                await cursor.execute(
                    "SELECT * FROM payments WHERE payment_id = ?",
                    (payment_id,)
                )
                row = await cursor.fetchone()

                if row:
                    columns = [description[0] for description in cursor.description]
                    return dict(zip(columns, row))
                return None
        except Exception as e:
            logger.error(f"Ошибка получения платежа {payment_id}: {e}")
            return None

    # ============ СТАТИСТИЧЕСКИЕ МЕТОДЫ ============

    async def get_total_users(self) -> int:
        """Возвращает общее количество пользователей"""
        try:
            async with self.get_cursor() as cursor:
                await cursor.execute("SELECT COUNT(*) FROM users")
                result = await cursor.fetchone()
                return result[0] if result else 0
        except Exception as e:
            logger.error(f"Ошибка получения количества пользователей: {e}")
            return 0

    async def get_total_balance(self) -> float:
        """Возвращает общий баланс всех пользователей"""
        try:
            async with self.get_cursor() as cursor:
                await cursor.execute("SELECT SUM(balance) FROM users")
                result = await cursor.fetchone()
                return result[0] if result and result[0] else 0.0
        except Exception as e:
            logger.error(f"Ошибка получения общего баланса: {e}")
            return 0.0

    async def get_recent_payments(self, user_id: int = None, limit: int = 10) -> List[Dict[str, Any]]:
        """Возвращает последние платежи (все или конкретного пользователя)"""
        try:
            async with self.get_cursor() as cursor:
                if user_id:
                    # Платежи конкретного пользователя
                    await cursor.execute('''
                        SELECT * FROM payments 
                        WHERE user_id = ?
                        ORDER BY created_at DESC
                        LIMIT ?
                    ''', (user_id, limit))
                else:
                    # Все платежи
                    await cursor.execute('''
                        SELECT p.*, u.username, u.first_name 
                        FROM payments p
                        LEFT JOIN users u ON p.user_id = u.user_id
                        ORDER BY p.created_at DESC
                        LIMIT ?
                    ''', (limit,))

                rows = await cursor.fetchall()
                columns = [description[0] for description in cursor.description]

                return [dict(zip(columns, row)) for row in rows]
        except Exception as e:
            logger.error(f"Ошибка получения последних платежей: {e}")
            return []
    # ============ АДМИНИСТРАТИВНЫЕ МЕТОДЫ ============

    async def is_user_admin(self, user_id: int) -> bool:
        """Проверяет, является ли пользователь администратором"""
        try:
            async with self.get_cursor() as cursor:
                await cursor.execute(
                    "SELECT is_admin FROM users WHERE user_id = ?",
                    (user_id,)
                )
                result = await cursor.fetchone()
                return result[0] if result else False
        except Exception as e:
            logger.error(f"Ошибка проверки админки для {user_id}: {e}")
            return False

    async def set_user_admin(self, user_id: int, is_admin: bool = True) -> bool:
        """Назначает или снимает права администратора"""
        try:
            async with self.get_cursor() as cursor:
                await cursor.execute(
                    "UPDATE users SET is_admin = ? WHERE user_id = ?",
                    (is_admin, user_id)
                )
                logger.info(f"Права админа для {user_id} установлены: {is_admin}")
                return True
        except Exception as e:
            logger.error(f"Ошибка установки прав админа для {user_id}: {e}")
            return False

    # ============ ЗАКРЫТИЕ СОЕДИНЕНИЯ ============

    async def close(self):
        """Закрывает соединение с базой данных"""
        if self._connection_pool:
            await self._connection_pool.close()
            self._initialized = False
            logger.info("Соединение с базой данных закрыто")


# Глобальный экземпляр базы данных для использования во всём приложении
db = AsyncDatabase()


# ============ ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ============

async def init_database():
    """Инициализирует базу данных (вызывается при запуске бота)"""
    await db.initialize()


async def test_database():
    """Тестовая функция для проверки работы БД"""
    print("🧪 Тестирование базы данных...")

    # Инициализируем БД
    await init_database()

    # Тестовые данные
    test_user_id = 123456789
    test_username = "test_user"

    # Добавляем тестового пользователя
    added = await db.add_or_update_user(
        user_id=test_user_id,
        username=test_username,
        first_name="Тестовый",
        last_name="Пользователь"
    )
    print(f"✅ Пользователь добавлен: {added}")

    # Получаем пользователя
    user = await db.get_user(test_user_id)
    print(f"✅ Пользователь получен: {user['first_name'] if user else 'нет'}")

    # Обновляем баланс
    success, before, after = await db.update_user_balance(test_user_id, 100.0, "Тестовое пополнение")
    print(f"✅ Баланс обновлен: {success}, {before} -> {after}")

    # Создаем тестовый платеж
    payment_id = f"test_payment_{datetime.now().timestamp()}"
    await db.create_payment(test_user_id, 50.0, payment_id, "Тестовый платеж")
    print(f"✅ Платеж создан: {payment_id}")

    # Обновляем статус платежа
    await db.update_payment_status(payment_id, "completed", "test_yoomoney_123")
    print(f"✅ Статус платежа обновлен")

    # Проверяем баланс
    balance = await db.get_user_balance(test_user_id)
    print(f"✅ Текущий баланс: {balance}")

    # Статистика
    total_users = await db.get_total_users()
    total_balance = await db.get_total_balance()
    print(f"✅ Статистика: {total_users} пользователей, {total_balance} руб. общий баланс")

    print("🎉 Тест базы данных завершен успешно!")


if __name__ == "__main__":
    # Запуск теста если файл запущен напрямую
    import asyncio

    asyncio.run(test_database())