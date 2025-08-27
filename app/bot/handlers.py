import asyncio
from typing import Dict, Any, Optional
from aiogram import Router, F
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    WebAppInfo, PreCheckoutQuery, SuccessfulPayment
)
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.config import settings
from app.database.models import User, Dialog, Message as DBMessage
from app.database.connection import get_db
from app.services.openai_service import openai_service
from app.services.billing_service import billing_service
from app.services.payment_service import payment_service
import structlog

logger = structlog.get_logger(__name__)
router = Router()


class ChatStates(StatesGroup):
    waiting_for_message = State()


def get_main_keyboard() -> InlineKeyboardMarkup:
    """Main menu keyboard"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="💬 Открыть чат",
                web_app=WebAppInfo(url=f"{settings.app_base_url}/chat")
            ),
            InlineKeyboardButton(
                text="📊 Мои лимиты",
                callback_data="limits"
            )
        ],
        [
            InlineKeyboardButton(
                text="💎 Тарифы",
                callback_data="plans"
            ),
            InlineKeyboardButton(
                text="🆕 Новый диалог",
                callback_data="new_dialog"
            )
        ],
        [
            InlineKeyboardButton(
                text="⚙️ Настройки",
                web_app=WebAppInfo(url=f"{settings.app_base_url}/settings")
            ),
            InlineKeyboardButton(
                text="📚 История",
                web_app=WebAppInfo(url=f"{settings.app_base_url}/history")
            )
        ]
    ])


def get_plans_keyboard() -> InlineKeyboardMarkup:
    """Plans selection keyboard"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="⭐ Start (300 запросов/мес)",
                callback_data="plan_start"
            )
        ],
        [
            InlineKeyboardButton(
                text="🚀 Pro (1500 запросов/мес)",
                callback_data="plan_pro"
            )
        ],
        [
            InlineKeyboardButton(
                text="💼 Business (безлимит)",
                callback_data="plan_business"
            )
        ],
        [
            InlineKeyboardButton(
                text="📦 Пакет 100 запросов",
                callback_data="pack_100"
            ),
            InlineKeyboardButton(
                text="📦 Пакет 500 запросов",
                callback_data="pack_500"
            )
        ],
        [
            InlineKeyboardButton(
                text="🔙 Назад",
                callback_data="back_to_main"
            )
        ]
    ])


def get_payment_keyboard(plan_name: str, amount_stars: int, amount_rub: float) -> InlineKeyboardMarkup:
    """Payment options keyboard"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=f"⭐ Оплатить {amount_stars} звездами",
                callback_data=f"pay_stars_{plan_name}"
            )
        ],
        [
            InlineKeyboardButton(
                text=f"💳 Оплатить {amount_rub}₽",
                callback_data=f"pay_yoomoney_{plan_name}"
            )
        ],
        [
            InlineKeyboardButton(
                text="🔙 Назад к тарифам",
                callback_data="plans"
            )
        ]
    ])


@router.message(Command("start"))
async def cmd_start(message: Message, session: AsyncSession):
    """Handle /start command"""
    user_id = message.from_user.id
    
    # Check if user exists
    user = await session.execute(
        select(User).where(User.id == user_id)
    )
    user = user.scalar_one_or_none()
    
    if not user:
        # Create new user
        user = User(
            id=user_id,
            trial_left=settings.trial_requests,
            lang=message.from_user.language_code or "ru"
        )
        session.add(user)
        await session.commit()
        
        welcome_text = f"""
🎉 Добро пожаловать в AI-ассистента!

У вас есть {settings.trial_requests} бесплатных запросов для начала работы.

🤖 Что умеет бот:
• Диалоги с ChatGPT
• Стриминговые ответы
• История переписки
• Различные модели AI

💡 Начните с кнопки "Открыть чат" или посмотрите ваши лимиты.
        """
    else:
        quota = await billing_service.get_user_quota(session, user_id)
        welcome_text = f"""
👋 С возвращением!

📊 Ваши лимиты:
• Осталось запросов: {quota['remaining']}
• Тариф: {quota['plan_name'] or 'Триал'}
        """
    
    await message.answer(
        welcome_text.strip(),
        reply_markup=get_main_keyboard()
    )


@router.message(Command("help"))
async def cmd_help(message: Message):
    """Handle /help command"""
    help_text = """
🤖 AI-ассистент - ваш умный помощник

📋 Доступные команды:
/start - Главное меню
/help - Эта справка
/limits - Ваши лимиты
/upgrade - Тарифы
/new - Новый диалог
/lang - Смена языка

💬 Как использовать:
1. Нажмите "Открыть чат"
2. Напишите ваш вопрос
3. Получите ответ от AI

💎 Тарифы:
• Триал: 30 запросов бесплатно
• Start: 300 запросов/мес
• Pro: 1500 запросов/мес
• Business: безлимит

❓ Есть вопросы? Обратитесь к администратору.
    """
    
    await message.answer(help_text.strip())


@router.message(Command("limits"))
async def cmd_limits(message: Message, session: AsyncSession):
    """Handle /limits command"""
    user_id = message.from_user.id
    quota = await billing_service.get_user_quota(session, user_id)
    
    limits_text = f"""
📊 Ваши лимиты:

🆓 Триал: {quota['trial_left']} запросов осталось
💎 Тариф: {quota['plan_name'] or 'Триал'}

📈 Использовано в этом месяце: {quota['used_this_month']}
🎯 Осталось запросов: {quota['remaining']}

{f"📅 Подписка до: {quota['plan_until'].strftime('%d.%m.%Y')}" if quota['plan_until'] else ""}
    """
    
    await message.answer(limits_text.strip())


@router.message(Command("upgrade"))
async def cmd_upgrade(message: Message):
    """Handle /upgrade command"""
    await message.answer(
        "💎 Выберите тариф:",
        reply_markup=get_plans_keyboard()
    )


@router.message(Command("new"))
async def cmd_new_dialog(message: Message, session: AsyncSession):
    """Handle /new command - start new dialog"""
    user_id = message.from_user.id
    
    # Create new dialog
    dialog = Dialog(user_id=user_id, title="Новый диалог")
    session.add(dialog)
    await session.commit()
    
    await message.answer(
        "🆕 Новый диалог создан! Нажмите 'Открыть чат' для начала.",
        reply_markup=get_main_keyboard()
    )


@router.message(Command("lang"))
async def cmd_lang(message: Message):
    """Handle /lang command"""
    lang_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_ru"),
            InlineKeyboardButton(text="🇺🇸 English", callback_data="lang_en")
        ],
        [
            InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")
        ]
    ])
    
    await message.answer(
        "🌍 Выберите язык:",
        reply_markup=lang_keyboard
    )


@router.callback_query(F.data == "limits")
async def callback_limits(callback: CallbackQuery, session: AsyncSession):
    """Handle limits callback"""
    user_id = callback.from_user.id
    quota = await billing_service.get_user_quota(session, user_id)
    
    limits_text = f"""
📊 Ваши лимиты:

🆓 Триал: {quota['trial_left']} запросов осталось
💎 Тариф: {quota['plan_name'] or 'Триал'}

📈 Использовано в этом месяце: {quota['used_this_month']}
🎯 Осталось запросов: {quota['remaining']}

{f"📅 Подписка до: {quota['plan_until'].strftime('%d.%m.%Y')}" if quota['plan_until'] else ""}
    """
    
    await callback.message.edit_text(
        limits_text.strip(),
        reply_markup=get_main_keyboard()
    )


@router.callback_query(F.data == "plans")
async def callback_plans(callback: CallbackQuery):
    """Handle plans callback"""
    await callback.message.edit_text(
        "💎 Выберите тариф:",
        reply_markup=get_plans_keyboard()
    )


@router.callback_query(F.data == "new_dialog")
async def callback_new_dialog(callback: CallbackQuery, session: AsyncSession):
    """Handle new dialog callback"""
    user_id = callback.from_user.id
    
    # Create new dialog
    dialog = Dialog(user_id=user_id, title="Новый диалог")
    session.add(dialog)
    await session.commit()
    
    await callback.message.edit_text(
        "🆕 Новый диалог создан! Нажмите 'Открыть чат' для начала.",
        reply_markup=get_main_keyboard()
    )


@router.callback_query(F.data.startswith("plan_") | F.data.startswith("pack_"))
async def callback_plan_selection(callback: CallbackQuery):
    """Handle plan selection"""
    plan_type = callback.data
    
    # Define plan details
    plans = {
        "plan_start": {"name": "Start", "stars": 1000, "rub": 299, "quota": 300},
        "plan_pro": {"name": "Pro", "stars": 2500, "rub": 799, "quota": 1500},
        "plan_business": {"name": "Business", "stars": 5000, "rub": 1999, "quota": -1},
        "pack_100": {"name": "Pack100", "stars": 300, "rub": 99, "quota": 100},
        "pack_500": {"name": "Pack500", "stars": 1200, "rub": 399, "quota": 500}
    }
    
    plan = plans.get(plan_type)
    if not plan:
        await callback.answer("Тариф не найден")
        return
    
    plan_text = f"""
💎 {plan['name']}

📊 Квота: {plan['quota'] if plan['quota'] > 0 else 'Безлимит'} запросов
⭐ Цена: {plan['stars']} звезд
💳 Цена: {plan['rub']}₽

Выберите способ оплаты:
    """
    
    await callback.message.edit_text(
        plan_text.strip(),
        reply_markup=get_payment_keyboard(plan['name'], plan['stars'], plan['rub'])
    )


@router.callback_query(F.data.startswith("pay_stars_"))
async def callback_pay_stars(callback: CallbackQuery):
    """Handle Stars payment"""
    plan_name = callback.data.replace("pay_stars_", "")
    
    # Get plan details
    plans = {
        "Start": {"stars": 1000, "quota": 300},
        "Pro": {"stars": 2500, "quota": 1500},
        "Business": {"stars": 5000, "quota": -1},
        "Pack100": {"stars": 300, "quota": 100},
        "Pack500": {"stars": 1200, "quota": 500}
    }
    
    plan = plans.get(plan_name)
    if not plan:
        await callback.answer("Тариф не найден")
        return
    
    # Create Stars payment
    stars_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=f"⭐ Купить за {plan['stars']} звезд",
                callback_data=f"confirm_stars_{plan_name}"
            )
        ],
        [
            InlineKeyboardButton(
                text="🔙 Назад",
                callback_data="plans"
            )
        ]
    ])
    
    await callback.message.edit_text(
        f"⭐ Оплата звездами\n\nТариф: {plan_name}\nЦена: {plan['stars']} звезд\n\nНажмите кнопку для оплаты:",
        reply_markup=stars_keyboard
    )


@router.callback_query(F.data.startswith("pay_yoomoney_"))
async def callback_pay_yoomoney(callback: CallbackQuery, session: AsyncSession):
    """Handle YooKassa payment"""
    plan_name = callback.data.replace("pay_yoomoney_", "")
    user_id = callback.from_user.id
    
    # Get plan details
    plans = {
        "Start": {"rub": 299, "quota": 300},
        "Pro": {"rub": 799, "quota": 1500},
        "Business": {"rub": 1999, "quota": -1},
        "Pack100": {"rub": 99, "quota": 100},
        "Pack500": {"rub": 399, "quota": 500}
    }
    
    plan = plans.get(plan_name)
    if not plan:
        await callback.answer("Тариф не найден")
        return
    
    try:
        # Create YooKassa payment
        payment = payment_service.create_yoomoney_payment(
            user_id=user_id,
            plan_name=plan_name,
            amount=plan['rub'],
            description=f"Подписка {plan_name} - {plan['quota'] if plan['quota'] > 0 else 'безлимит'} запросов"
        )
        
        yoomoney_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="💳 Перейти к оплате",
                    url=payment['confirmation_url']
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔙 Назад",
                    callback_data="plans"
                )
            ]
        ])
        
        await callback.message.edit_text(
            f"💳 Оплата через ЮMoney\n\nТариф: {plan_name}\nЦена: {plan['rub']}₽\n\nНажмите кнопку для перехода к оплате:",
            reply_markup=yoomoney_keyboard
        )
        
    except Exception as e:
        logger.error("Failed to create YooKassa payment", error=str(e))
        await callback.answer("Ошибка создания платежа")


@router.callback_query(F.data == "back_to_main")
async def callback_back_to_main(callback: CallbackQuery):
    """Handle back to main menu"""
    await callback.message.edit_text(
        "🏠 Главное меню:",
        reply_markup=get_main_keyboard()
    )


@router.pre_checkout_query()
async def process_pre_checkout(pre_checkout: PreCheckoutQuery):
    """Handle pre-checkout query for Stars payments"""
    await pre_checkout.answer(ok=True)


@router.message(F.successful_payment)
async def process_successful_payment(message: Message, session: AsyncSession):
    """Handle successful Stars payment"""
    payment = message.successful_payment
    user_id = message.from_user.id
    
    # Extract plan name from invoice payload
    plan_name = payment.invoice_payload
    
    # Get amount in stars
    amount_stars = payment.total_amount / 100  # Convert from kopecks
    
    # Process payment
    success = await payment_service.process_stars_payment(
        session=session,
        user_id=user_id,
        plan_name=plan_name,
        telegram_charge_id=payment.telegram_payment_charge_id,
        amount=int(amount_stars)
    )
    
    if success:
        await message.answer(
            f"✅ Оплата прошла успешно!\n\nТариф {plan_name} активирован. Теперь вы можете использовать все возможности бота.",
            reply_markup=get_main_keyboard()
        )
    else:
        await message.answer(
            "❌ Ошибка при обработке платежа. Обратитесь к администратору.",
            reply_markup=get_main_keyboard()
        )


# Admin commands
@router.message(Command("admin"))
async def cmd_admin(message: Message):
    """Handle /admin command"""
    user_id = message.from_user.id
    
    if user_id not in settings.admin_ids:
        await message.answer("❌ У вас нет доступа к админ-панели.")
        return
    
    admin_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="📊 Админ-панель",
                web_app=WebAppInfo(url=f"{settings.app_base_url}/admin")
            )
        ],
        [
            InlineKeyboardButton(
                text="📈 Статистика",
                callback_data="admin_stats"
            ),
            InlineKeyboardButton(
                text="👥 Пользователи",
                callback_data="admin_users"
            )
        ]
    ])
    
    await message.answer(
        "🔧 Админ-панель\n\nВыберите действие:",
        reply_markup=admin_keyboard
    )


@router.message(Command("give"))
async def cmd_give(message: Message, session: AsyncSession):
    """Handle /give command - give requests/plan to user"""
    user_id = message.from_user.id
    
    if user_id not in settings.admin_ids:
        await message.answer("❌ У вас нет доступа к этой команде.")
        return
    
    # Parse command: /give <user_id> <amount|plan>
    args = message.text.split()
    if len(args) != 3:
        await message.answer("❌ Использование: /give <user_id> <amount|plan>")
        return
    
    try:
        target_user_id = int(args[1])
        amount_or_plan = args[2]
        
        # Check if it's a number (trial requests) or plan name
        if amount_or_plan.isdigit():
            amount = int(amount_or_plan)
            success = await billing_service.add_trial_requests(session, target_user_id, amount)
            if success:
                await message.answer(f"✅ Пользователю {target_user_id} добавлено {amount} запросов.")
            else:
                await message.answer(f"❌ Ошибка при добавлении запросов пользователю {target_user_id}.")
        else:
            # It's a plan name
            # TODO: Implement plan activation
            await message.answer(f"📋 Активация плана {amount_or_plan} для пользователя {target_user_id} (не реализовано).")
            
    except ValueError:
        await message.answer("❌ Неверный формат user_id.")


@router.message(Command("stats"))
async def cmd_stats(message: Message, session: AsyncSession):
    """Handle /stats command - show statistics"""
    user_id = message.from_user.id
    
    if user_id not in settings.admin_ids:
        await message.answer("❌ У вас нет доступа к этой команде.")
        return
    
    # TODO: Implement statistics
    await message.answer("📊 Статистика (не реализовано)")
