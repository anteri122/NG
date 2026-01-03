"""
Упрощенный менеджер кэша для слабого ПК.
Вместо Redis используем in-memory кэш с периодической очисткой.
"""

import asyncio
import time
from typing import Optional, Any, Dict
from datetime import datetime, timedelta
import logging

logger = logging.getLogger("cache")


class SimpleCacheManager:
    """
    Простой in-memory кэш для хранения часто используемых данных.
    Оптимизирован для слабых ПК (не использует Redis).
    """

    def __init__(self):
        self.cache: Dict[str, dict] = {}
        self.cache_expiry: Dict[str, float] = {}
        self.hits = 0
        self.misses = 0
        self.total_requests = 0

        # Автоматическая очистка устаревших записей каждые 5 минут
        self._cleanup_task = None

    async def initialize(self):
        """Инициализация кэша и запуск фоновой очистки"""
        logger.info("🔄 Инициализация in-memory кэша...")

        # Запускаем фоновую задачу очистки
        self._cleanup_task = asyncio.create_task(self._periodic_cleanup())

        logger.info("✅ In-memory кэш инициализирован")

    async def get(self, key: str) -> Optional[Any]:
        """Получение значения из кэша"""
        self.total_requests += 1

        # Проверяем наличие и срок действия
        if key in self.cache:
            expiry = self.cache_expiry.get(key, 0)
            if expiry > time.time():
                self.hits += 1
                return self.cache[key]
            else:
                # Удаляем просроченную запись
                del self.cache[key]
                del self.cache_expiry[key]

        self.misses += 1
        return None

    async def set(self, key: str, value: Any, ttl: int = 300):
        """Сохранение значения в кэше"""
        self.cache[key] = value
        self.cache_expiry[key] = time.time() + ttl

    async def delete(self, key: str):
        """Удаление значения из кэша"""
        if key in self.cache:
            del self.cache[key]
        if key in self.cache_expiry:
            del self.cache_expiry[key]

    async def clear(self):
        """Полная очистка кэша"""
        self.cache.clear()
        self.cache_expiry.clear()
        logger.info("🧹 Кэш полностью очищен")

    async def get_stats(self) -> dict:
        """Получение статистики кэша"""
        return {
            'total_entries': len(self.cache),
            'total_requests': self.total_requests,
            'hits': self.hits,
            'misses': self.misses,
            'hit_rate': self.hits / self.total_requests if self.total_requests > 0 else 0,
            'memory_usage': self._estimate_memory_usage()
        }

    def _estimate_memory_usage(self) -> str:
        """Оценка использования памяти (грубая)"""
        import sys
        total_size = 0
        for key, value in self.cache.items():
            total_size += sys.getsizeof(key)
            total_size += sys.getsizeof(value)

        for key in self.cache_expiry:
            total_size += sys.getsizeof(key)
            total_size += 8  # float size

        if total_size < 1024:
            return f"{total_size} B"
        elif total_size < 1024 * 1024:
            return f"{total_size / 1024:.1f} KB"
        else:
            return f"{total_size / (1024 * 1024):.1f} MB"

    async def _periodic_cleanup(self):
        """Периодическая очистка устаревших записей"""
        while True:
            try:
                await asyncio.sleep(300)  # Каждые 5 минут
                await self._clean_expired()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Ошибка при очистке кэша: {e}")

    async def _clean_expired(self):
        """Очистка устаревших записей"""
        current_time = time.time()
        expired_keys = []

        for key, expiry in self.cache_expiry.items():
            if expiry < current_time:
                expired_keys.append(key)

        if expired_keys:
            for key in expired_keys:
                del self.cache[key]
                del self.cache_expiry[key]

            logger.debug(f"Очищено {len(expired_keys)} устаревших записей из кэша")

    async def close(self):
        """Завершение работы кэша"""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        # Логируем финальную статистику
        stats = await self.get_stats()
        logger.info(f"📊 Статистика кэша при завершении: {stats}")

        # Очищаем кэш
        await self.clear()


# Глобальный экземпляр кэша
cache = SimpleCacheManager()