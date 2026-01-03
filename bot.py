import asyncio
import logging
import sys
import os
import json
from datetime import datetime
from typing import Dict, List, Optional

from aiogram import Bot, Dispatcher, types
from aiogram.dispatcher import FSMContext
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.utils import executor
from aiogram.types import WebAppInfo

from config import config
from database_async import db, init_database

# Настройка логирования
os.makedirs("logs", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("logs/bot.log", encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

# ============ ИНИЦИАЛИЗАЦИЯ ============

bot = Bot(token=config.BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# URL Mini App (замените на свой)
WEBAPP_URL = config.WEBAPP_URL if hasattr(config, 'WEBAPP_URL') else "https://ваш-домен.com"


# ============ СОСТОЯНИЯ (FSM) ============

class PaymentStates(StatesGroup):
    waiting_for_payment = State()


class OrderStates(StatesGroup):
    waiting_for_address = State()
    waiting_for_phone = State()


# ============ ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ============

def get_main_keyboard() -> types.ReplyKeyboardMarkup:
    """Главная клавиатура меню"""
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    keyboard.add(
        types.KeyboardButton("🏪 Магазин"),
        types.KeyboardButton("📦 Каталог")
    )
    keyboard.add(
        types.KeyboardButton("🛒 Корзина"),
        types.KeyboardButton("👤 Профиль")
    )
    keyboard.add(
        types.KeyboardButton("💳 Пополнить"),
        types.KeyboardButton("🚚 Доставка")
    )
    return keyboard


def get_shop_keyboard() -> types.InlineKeyboardMarkup:
    """Клавиатура для магазина"""
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        types.InlineKeyboardButton(
            "🚀 Открыть магазин",
            web_app=WebAppInfo(url=WEBAPP_URL)
        )
    )
    keyboard.add(
        types.InlineKeyboardButton("🛒 Корзина", callback_data="view_cart"),
        types.InlineKeyboardButton("📞 Поддержка", callback_data="support")
    )
    return keyboard


def format_product_card(product: Dict) -> str:
    """Форматирование карточки товара"""
    stock_emoji = "🟢" if product['stock'] > 10 else "🟡" if product['stock'] > 0 else "🔴"

    return f"""
📦 *{product['name']}*
💰 Цена: {product['price']} ₽
{stock_emoji} В наличии: {product['stock']} шт.
🏷️ Категория: {product['category']}
━━━━━━━━━━━━━━━━━━━━
    """.strip()


def format_cart_summary(cart_items: List[Dict]) -> str:
    """Форматирование корзины"""
    if not cart_items:
        return "🛒 *Ваша корзина пуста*"

    total = sum(item['price'] * item['quantity'] for item in cart_items)
    items_text = "\n".join(
        f"• {item['name']} ×{item['quantity']} = {item['price'] * item['quantity']} ₽"
        for item in cart_items[:5]  # Показываем первые 5 товаров
    )

    if len(cart_items) > 5:
        items_text += f"\n• ... и ещё {len(cart_items) - 5} товаров"

    return f"""
🛒 *Ваша корзина*

{items_text}

━━━━━━━━━━━━━━━━━━━━
💰 *Итого:* {total} ₽

Откройте Mini App для управления корзиной:
    """.strip()


# ============ КОМАНДЫ ============

@dp.message_handler(commands=['start'], state="*")
async def cmd_start(message: types.Message, state: FSMContext):
    """Команда /start"""
    await state.finish()

    user = message.from_user
    user_id = user.id

    # Регистрация пользователя
    await db.add_or_update_user(
        user_id=user_id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name
    )

    # Получение баланса
    user_data = await db.get_user(user_id)
    balance = user_data['balance'] if user_data else 0.0

    # Приветственное сообщение
    welcome_text = f"""
👋 *Привет, {user.first_name}!*

🏪 *Добро пожаловать в Nigilist Shop!*
Магазин одноразок и жидкостей с доставкой

💰 *Ваш баланс:* {balance:.2f} ₽

*Основные команды:*
🏪 /shop - Открыть магазин
📦 /catalog - Каталог товаров
🛒 /cart - Моя корзина
💳 /pay - Пополнить баланс
👤 /profile - Мой профиль
🚚 /delivery - Условия доставки
📞 /support - Поддержка
📋 /help - Помощь
    """.strip()

    if user_id == config.ADMIN_ID:
        welcome_text += "\n\n*Админ команды:*\n👑 /admin - Панель управления"

    await message.answer(welcome_text,
                         reply_markup=get_main_keyboard(),
                         parse_mode="Markdown")


@dp.message_handler(commands=['menu'], state="*")
async def cmd_menu(message: types.Message):
    """Главное меню"""
    menu_text = """
🏪 *Главное меню Nigilist Shop*

Выберите раздел:
• 🏪 Магазин - Открыть интернет-магазин
• 📦 Каталог - Просмотр товаров
• 🛒 Корзина - Ваши товары
• 👤 Профиль - Личный кабинет
• 💳 Пополнить - Пополнение баланса
• 🚚 Доставка - Условия доставки
• 📞 Поддержка - Связь с нами
    """.strip()

    await message.answer(menu_text,
                         reply_markup=get_main_keyboard(),
                         parse_mode="Markdown")


@dp.message_handler(commands=['shop'], state="*")
async def cmd_shop(message: types.Message):
    """Открыть магазин с анимацией"""
    loading_msg = await message.answer("🔄 *Загружаем магазин...*",
                                       parse_mode="Markdown")

    # Анимация загрузки
    for i in range(3):
        await asyncio.sleep(0.5)
        await loading_msg.edit_text(f"🔄 *Загружаем магазин{'.' * (i + 1)}*")

    await loading_msg.delete()

    shop_text = """
🏪 *Nigilist Shop* 🚀

🔥 *Одноразки и все для вейпинга*
Быстрая доставка по Москве и России

📦 *Категории товаров:*
• Одноразки (Elf Bar, HQD, Puff Bar)
• Жидкости для парения
• Картриджи и аксессуары

🚚 *Доставка:*
• Самовывоз: бесплатно
• По Москве: от 200 ₽
• По России: 500 ₽

💳 *Оплата:*
• Баланс бота
• ЮMoney
• Перевод на карту
• Наличные при получении

👇 *Нажмите кнопку ниже, чтобы открыть магазин:*
    """.strip()

    await message.answer(shop_text,
                         reply_markup=get_shop_keyboard(),
                         parse_mode="Markdown")


@dp.message_handler(commands=['catalog'], state="*")
async def cmd_catalog(message: types.Message):
    """Каталог товаров"""
    catalog_text = """
📦 *Каталог товаров*

Откройте интерактивный каталог для просмотра:
• Все товары с фото и описанием
• Поиск по категориям
• Добавление в корзину
• Оформление заказа

👇 *Нажмите кнопку, чтобы открыть каталог:*
    """.strip()

    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(
        types.InlineKeyboardButton(
            "📦 Открыть каталог",
            web_app=WebAppInfo(url=WEBAPP_URL)
        )
    )

    await message.answer(catalog_text,
                         reply_markup=keyboard,
                         parse_mode="Markdown")


@dp.message_handler(commands=['cart'], state="*")
async def cmd_cart(message: types.Message):
    """Корзина пользователя"""
    user_id = message.from_user.id

    # Получаем корзину из базы (заглушка)
    # В реальности: cart_items = await db.get_cart(user_id)
    cart_items = []  # Заглушка

    cart_text = format_cart_summary(cart_items)

    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(
        types.InlineKeyboardButton(
            "🛒 Открыть корзину",
            web_app=WebAppInfo(url=f"{WEBAPP_URL}#cart")
        )
    )
    keyboard.add(
        types.InlineKeyboardButton("🏪 Продолжить покупки", callback_data="open_shop"),
        types.InlineKeyboardButton("🗑️ Очистить корзину", callback_data="clear_cart")
    )

    await message.answer(cart_text,
                         reply_markup=keyboard,
                         parse_mode="Markdown")


@dp.message_handler(commands=['profile'], state="*")
async def cmd_profile(message: types.Message):
    """Профиль пользователя"""
    user_id = message.from_user.id
    user_data = await db.get_user(user_id)

    if not user_data:
        await message.answer("❌ Произошла ошибка. Попробуйте /start")
        return

    reg_date = datetime.fromisoformat(user_data['created_at'])
    reg_date_str = reg_date.strftime("%d.%m.%Y")

    # Получаем статистику
    total_orders = await db.get_user_orders_count(user_id)
    total_spent = await db.get_user_total_spent(user_id)

    profile_text = f"""
👤 *Ваш профиль*

🆔 ID: `{user_data['user_id']}`
👁️ Имя: {user_data['first_name']} {user_data.get('last_name', '')}
📛 Юзернейм: @{user_data.get('username', 'нет')}

💰 *Баланс:* {user_data['balance']:.2f} ₽

📊 *Статистика:*
🛍️ Заказов: {total_orders}
💸 Потрачено: {total_spent:.2f} ₽

📅 Регистрация: {reg_date_str}
🔄 Последняя активность: {datetime.now().strftime('%d.%m.%Y %H:%M')}
    """.strip()

    if user_data.get('is_admin') or user_id == config.ADMIN_ID:
        profile_text += "\n\n👑 *Статус:* Администратор"

    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(
        types.InlineKeyboardButton("💳 Пополнить баланс", callback_data="balance_topup"),
        types.InlineKeyboardButton("🏪 Открыть магазин", callback_data="open_shop")
    )
    keyboard.add(
        types.InlineKeyboardButton("📋 Мои заказы", callback_data="my_orders"),
        types.InlineKeyboardButton("⚙️ Настройки", callback_data="settings")
    )

    await message.answer(profile_text,
                         reply_markup=keyboard,
                         parse_mode="Markdown")


@dp.message_handler(commands=['pay'], state="*")
async def cmd_pay(message: types.Message, state: FSMContext):
    """Пополнение баланса"""
    import uuid
    user_id = message.from_user.id
    payment_id = str(uuid.uuid4())

    await state.set_state(PaymentStates.waiting_for_payment)
    await state.update_data(payment_id=payment_id)

    # Получаем пользователя
    user_data = await db.get_user(user_id)
    current_balance = user_data['balance'] if user_data else 0.0

    payment_text = f"""
💳 *Пополнение баланса*

💰 Текущий баланс: {current_balance:.2f} ₽

👇 *Способы пополнения:*

1️⃣ *ЮMoney*
📞 Номер: `{config.YOOMONEY_WALLET}`
💵 Сумма: любая от {config.MIN_PAYMENT_AMOUNT} до {config.MAX_PAYMENT_AMOUNT} ₽
📝 Комментарий: `{user_id}`

2️⃣ *Карта (СБП)*
💳 Номер: `{config.CARD_NUMBER}`
👤 Получатель: {config.CARD_HOLDER}

⏱️ *После оплаты нажмите кнопку ниже:*
    """.strip()

    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton("✅ Я оплатил", callback_data=f"check_payment:{payment_id}"),
        types.InlineKeyboardButton("📱 ЮMoney", url=f"https://yoomoney.ru/to/{config.YOOMONEY_WALLET}")
    )
    keyboard.add(
        types.InlineKeyboardButton("❌ Отмена", callback_data="cancel_payment"),
        types.InlineKeyboardButton("💳 Карта", callback_data="card_payment")
    )

    await message.answer(payment_text,
                         reply_markup=keyboard,
                         parse_mode="Markdown")

    # Создаем запись о платеже
    await db.create_payment(
        user_id=user_id,
        amount=0,
        payment_id=payment_id,
        description="Ожидание оплаты"
    )

    logger.info(f"Создан платеж {payment_id} для пользователя {user_id}")


@dp.message_handler(commands=['delivery'], state="*")
async def cmd_delivery(message: types.Message):
    """Условия доставки"""
    delivery_text = """
🚚 *Условия доставки*

📦 *Самовывоз:*
📍 Адрес: г. Москва, ул. Примерная, д. 1
🕐 Время: 10:00 - 22:00 (ежедневно)
📞 Телефон: +7 (999) 123-45-67
💵 Оплата: наличные/карта
💰 Стоимость: бесплатно

🚗 *Доставка по Москве:*
⏱️ Время: 1-3 часа
💵 Стоимость: 200 ₽
🎁 Бесплатно: от 3000 ₽
📦 Способ: курьерская доставка

📮 *Доставка по России:*
⏱️ Время: 1-7 дней
💵 Стоимость: 500 ₽
🎁 Бесплатно: от 5000 ₽
📦 ТК: СДЭК, Почта России

💳 *Способы оплаты:*
• Наличные при получении
• Карта при получении
• ЮMoney
• Перевод на карту
• Баланс бота

📞 *Контакты:*
Телеграм: @anteridino
Телефон: +7 (999) 123-45-67
    """.strip()

    await message.answer(delivery_text, parse_mode="Markdown")


@dp.message_handler(commands=['support'], state="*")
async def cmd_support(message: types.Message):
    """Поддержка"""
    support_text = """
📞 *Поддержка Nigilist Shop*

По всем вопросам обращайтесь:

👤 *Менеджер:* @anteridino
📧 *Email:* afaminov813@mail.ru
☎️ *Телефон:* +7 (999) 123-45-67

🕐 *Время работы поддержки:*
Пн-Пт: 10:00 - 20:00
Сб-Вс: 12:00 - 18:00

📋 *Часто задаваемые вопросы:*

❓ *Как оформить заказ?*
1. Откройте /shop или /catalog
2. Добавьте товары в корзину
3. Оформите заказ через корзину
4. Выберите способ доставки и оплаты

❓ *Как пополнить баланс?*
Используйте команду /pay

❓ *Как отследить заказ?*
Напишите менеджеру с номером заказа

❓ *Как вернуть товар?*
Обратитесь к менеджеру в течение 14 дней
    """.strip()

    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(
        types.InlineKeyboardButton("👤 Написать менеджеру", url="https://t.me/anteridino"),
        types.InlineKeyboardButton("🏪 Открыть магазин", callback_data="open_shop")
    )

    await message.answer(support_text,
                         reply_markup=keyboard,
                         parse_mode="Markdown")


@dp.message_handler(commands=['help'], state="*")
async def cmd_help(message: types.Message):
    """Помощь"""
    help_text = """
🆘 *Помощь по боту*

*Основные команды:*
🏪 /start - Запустить бота
🏪 /shop - Открыть магазин
📦 /catalog - Каталог товаров
🛒 /cart - Моя корзина
👤 /profile - Ваш профиль
💳 /pay - Пополнить баланс
🚚 /delivery - Условия доставки
📞 /support - Поддержка
📋 /help - Эта справка
📱 /menu - Главное меню

*Как покупать:*
1. Откройте /shop или /catalog
2. Выберите товары, добавьте в корзину
3. Откройте корзину (/cart)
4. Оформите заказ через Mini App

*Пополнение баланса:*
1. Нажмите /pay
2. Выберите способ оплаты
3. Переведите деньги
4. Нажмите "Я оплатил"

*Минимальная сумма:* {config.MIN_PAYMENT_AMOUNT} ₽
*Максимальная сумма:* {config.MAX_PAYMENT_AMOUNT} ₽

*Контакты:*
👤 Менеджер: @anteridino
💳 Кошелек: {config.YOOMONEY_WALLET}
    """.strip()

    await message.answer(help_text, parse_mode="Markdown")


@dp.message_handler(commands=['admin'], state="*")
async def cmd_admin(message: types.Message):
    """Админ панель"""
    user_id = message.from_user.id

    if user_id != config.ADMIN_ID:
        await message.answer("❌ У вас нет прав администратора")
        return

    # Статистика
    total_users = await db.get_total_users()
    total_balance = await db.get_total_balance()
    recent_payments = await db.get_recent_payments(limit=10)

    admin_text = f"""
👑 *Панель администратора*

📊 *Статистика:*
👥 Пользователей: {total_users}
💰 Общий баланс: {total_balance:.2f} ₽

💰 *Последние платежи ({len(recent_payments)}):*
    """.strip()

    for payment in recent_payments:
        status_emoji = {
            'completed': '✅',
            'pending': '⏳',
            'failed': '❌',
            'cancelled': '🚫'
        }.get(payment['status'], '❓')

        user_info = await db.get_user(payment['user_id'])
        username = f"@{user_info['username']}" if user_info and user_info.get(
            'username') else f"ID:{payment['user_id']}"

        admin_text += f"\n{status_emoji} {username}: {payment['amount']} ₽ ({payment['status']})"

    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton("📦 Управление товарами", callback_data="admin_products"),
        types.InlineKeyboardButton("👥 Управление пользователями", callback_data="admin_users")
    )
    keyboard.add(
        types.InlineKeyboardButton("💰 Управление платежами", callback_data="admin_payments"),
        types.InlineKeyboardButton("📊 Полная статистика", callback_data="admin_stats")
    )
    keyboard.add(
        types.InlineKeyboardButton("📢 Рассылка", callback_data="admin_broadcast"),
        types.InlineKeyboardButton("⚙️ Настройки", callback_data="admin_settings")
    )

    await message.answer(admin_text,
                         reply_markup=keyboard,
                         parse_mode="Markdown")


# ============ ТЕКСТОВЫЕ КОМАНДЫ ============

@dp.message_handler(lambda message: message.text.lower() in ['магазин', '🏪 магазин'])
async def text_shop(message: types.Message):
    await cmd_shop(message)


@dp.message_handler(lambda message: message.text.lower() in ['каталог', '📦 каталог'])
async def text_catalog(message: types.Message):
    await cmd_catalog(message)


@dp.message_handler(lambda message: message.text.lower() in ['корзина', '🛒 корзина'])
async def text_cart(message: types.Message):
    await cmd_cart(message)


@dp.message_handler(lambda message: message.text.lower() in ['профиль', '👤 профиль'])
async def text_profile(message: types.Message):
    await cmd_profile(message)


@dp.message_handler(lambda message: message.text.lower() in ['пополнить', '💳 пополнить'])
async def text_pay(message: types.Message):
    await cmd_pay(message, FSMContext(dp.storage, message.from_user.id, message.chat.id))


@dp.message_handler(lambda message: message.text.lower() in ['доставка', '🚚 доставка'])
async def text_delivery(message: types.Message):
    await cmd_delivery(message)


@dp.message_handler(lambda message: message.text.lower() in ['поддержка', '📞 поддержка'])
async def text_support(message: types.Message):
    await cmd_support(message)


@dp.message_handler(lambda message: message.text.lower() in ['помощь', '📋 помощь'])
async def text_help(message: types.Message):
    await cmd_help(message)


@dp.message_handler(lambda message: message.text.lower() in ['меню', 'меню'])
async def text_menu(message: types.Message):
    await cmd_menu(message)


# ============ ОБРАБОТЧИКИ КОЛБЭКОВ ============

@dp.callback_query_handler(lambda c: c.data == "open_shop")
async def process_open_shop(callback_query: types.CallbackQuery):
    await callback_query.answer()
    await cmd_shop(callback_query.message)


@dp.callback_query_handler(lambda c: c.data == "view_cart")
async def process_view_cart(callback_query: types.CallbackQuery):
    await callback_query.answer()
    await cmd_cart(callback_query.message)


@dp.callback_query_handler(lambda c: c.data == "balance_topup")
async def process_balance_topup(callback_query: types.CallbackQuery):
    await callback_query.answer()
    await cmd_pay(callback_query.message,
                  FSMContext(dp.storage, callback_query.from_user.id, callback_query.message.chat.id))


@dp.callback_query_handler(lambda c: c.data == "support")
async def process_support(callback_query: types.CallbackQuery):
    await callback_query.answer()
    await cmd_support(callback_query.message)


@dp.callback_query_handler(lambda c: c.data == "clear_cart")
async def process_clear_cart(callback_query: types.CallbackQuery):
    await callback_query.answer()

    # Здесь будет очистка корзины из базы данных
    user_id = callback_query.from_user.id
    # await db.clear_cart(user_id)

    await callback_query.message.edit_text(
        "🗑️ *Корзина очищена*\n\n"
        "Все товары удалены из вашей корзины.",
        parse_mode="Markdown"
    )


@dp.callback_query_handler(lambda c: c.data.startswith('check_payment:'))
async def process_check_payment(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()

    user_id = callback_query.from_user.id
    payment_id = callback_query.data.split(':')[1]

    payment = await db.get_payment(payment_id)

    if not payment:
        await callback_query.message.edit_text("❌ Платеж не найден")
        return

    if payment['status'] == 'completed':
        await callback_query.message.edit_text(
            f"✅ *Платеж уже обработан!*\n\n"
            f"💰 Сумма: {payment['amount']} ₽\n"
            f"📅 Дата: {payment['created_at']}",
            parse_mode="Markdown"
        )
        await state.finish()
        return

    await callback_query.message.edit_text("🔍 *Проверяем ваш платеж...*", parse_mode="Markdown")

    # Имитация проверки платежа
    await asyncio.sleep(2)

    # В реальности здесь проверка через API платежной системы
    import random
    if random.random() > 0.2:  # 80% успешных платежей для демо
        amount = random.randint(config.MIN_PAYMENT_AMOUNT, min(5000, config.MAX_PAYMENT_AMOUNT))
        yoomoney_id = f"ym_{random.randint(100000, 999999)}"

        # Обновляем платеж
        await db.update_payment_status(payment_id, 'completed', yoomoney_id, amount)

        # Пополняем баланс
        await db.update_user_balance(user_id, amount)

        result_text = f"""
✅ *Платеж успешно обработан!*

💰 Сумма: {amount} ₽
🆔 ID платежа: {yoomoney_id}
📅 Время: {datetime.now().strftime('%d.%m.%Y %H:%M')}

💳 *Баланс пополнен!*
Проверьте: /profile
        """.strip()
    else:
        await db.update_payment_status(payment_id, 'failed')
        result_text = """
❌ *Платеж не найден*

Возможные причины:
• Деньги еще не поступили
• Неверный комментарий к переводу
• Сумма меньше минимальной
• Прошло менее 5 минут с момента оплаты

Попробуйте еще раз через 5 минут
        """.strip()

    await callback_query.message.edit_text(result_text, parse_mode="Markdown")
    await state.finish()


@dp.callback_query_handler(lambda c: c.data == 'cancel_payment', state="*")
async def process_cancel_payment(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()

    user_data = await state.get_data()
    payment_id = user_data.get('payment_id')

    if payment_id:
        await db.update_payment_status(payment_id, 'cancelled')

    await callback_query.message.edit_text("❌ *Платеж отменен*", parse_mode="Markdown")
    await state.finish()


# ============ API ДЛЯ MINI APP ============

@dp.message_handler(content_types=['web_app_data'])
async def handle_web_app_data(message: types.Message):
    """Обработка данных из Mini App"""
    try:
        data = json.loads(message.web_app_data.data)
        user_id = message.from_user.id

        if data.get('type') == 'cart_sync':
            # Синхронизация корзины
            cart_data = data.get('cart', [])
            # await db.save_cart(user_id, cart_data)

            await message.answer("🔄 Корзина синхронизирована с ботом!")

        elif data.get('type') == 'create_order':
            # Создание заказа
            order_data = data.get('order', {})
            # order_id = await db.create_order(user_id, order_data)

            await message.answer(
                f"✅ Заказ создан!\n"
                f"Номер заказа: #{random.randint(1000, 9999)}\n"
                f"С вами свяжется менеджер.",
                parse_mode="Markdown"
            )

    except Exception as e:
        logger.error(f"Ошибка обработки WebApp данных: {e}")
        await message.answer("❌ Произошла ошибка при обработке данных")


# ============ ЗАПУСК ============

async def on_startup(dp: Dispatcher):
    """Действия при запуске"""
    logger.info("🤖 БОТ ЗАПУСКАЕТСЯ")

    await init_database()

    # Установка команд меню
    await bot.set_my_commands([
        types.BotCommand("start", "Запустить бота"),
        types.BotCommand("shop", "Открыть магазин"),
        types.BotCommand("cart", "Моя корзина"),
        types.BotCommand("profile", "Мой профиль"),
        types.BotCommand("pay", "Пополнить баланс"),
        types.BotCommand("delivery", "Условия доставки"),
        types.BotCommand("support", "Поддержка"),
        types.BotCommand("help", "Помощь"),
        types.BotCommand("menu", "Главное меню"),
    ])

    # Отправка админу
    try:
        await bot.send_message(
            config.ADMIN_ID,
            f"✅ *Бот запущен!*\n\n"
            f"🏪 *Nigilist Shop готов к работе*\n"
            f"Время: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n"
            f"WebApp: {WEBAPP_URL}",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.warning(f"Не удалось отправить сообщение админу: {e}")

    logger.info("✅ Бот успешно запущен")


async def on_shutdown(dp: Dispatcher):
    """Действия при остановке"""
    logger.info("🛑 БОТ ОСТАНАВЛИВАЕТСЯ")
    await db.close()


if __name__ == '__main__':
    # Проверка токена
    if not config.BOT_TOKEN or config.BOT_TOKEN == "ваш_токен_бота":
        logger.critical("❌ Токен бота не настроен!")
        exit(1)

    # Запуск бота
    executor.start_polling(
        dp,
        on_startup=on_startup,
        on_shutdown=on_shutdown,
        skip_updates=True
    )