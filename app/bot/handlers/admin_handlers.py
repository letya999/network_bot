"""Admin panel handlers for bot management."""
import logging
from html import escape
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from app.db.session import AsyncSessionLocal
from app.services.user_service import UserService
from app.services.subscription_service import SubscriptionService
from app.services.sharing_service import SharingService
from app.services.payment_service import PaymentService
from app.models.subscription import SubscriptionPlan, SubscriptionStatus
from app.core.config import settings
from sqlalchemy import select, func

logger = logging.getLogger(__name__)

ADMIN_PREFIX = "admin_"


def is_admin(telegram_id: int) -> bool:
    """Check if a telegram user is an admin."""
    admin_ids = settings.ADMIN_TELEGRAM_IDS.split(",")
    return str(telegram_id) in [a.strip() for a in admin_ids if a.strip()]


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show admin panel."""
    user = update.effective_user

    if not is_admin(user.id):
        await update.message.reply_text("Доступ запрещен.")
        return

    text = (
        "<b>Админ-панель</b>\n\n"
        "Управление ботом и пользователями."
    )

    keyboard = [
        [InlineKeyboardButton("Статистика", callback_data=f"{ADMIN_PREFIX}stats")],
        [InlineKeyboardButton("Пользователи", callback_data=f"{ADMIN_PREFIX}users")],
        [InlineKeyboardButton("Подписки", callback_data=f"{ADMIN_PREFIX}subs")],
        [InlineKeyboardButton("Платежи", callback_data=f"{ADMIN_PREFIX}payments")],
        [InlineKeyboardButton("Публикации", callback_data=f"{ADMIN_PREFIX}shares")],
        [
            InlineKeyboardButton("Настройки цен", callback_data=f"{ADMIN_PREFIX}pricing"),
            InlineKeyboardButton("Рассылка", callback_data=f"{ADMIN_PREFIX}broadcast"),
        ],
        [InlineKeyboardButton("Выдать подписку", callback_data=f"{ADMIN_PREFIX}grant_sub")],
        [InlineKeyboardButton("Главное меню", callback_data="menu_main")],
    ]

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML"
        )
    else:
        await update.message.reply_text(
            text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML"
        )


async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle admin panel callbacks."""
    query = update.callback_query
    await query.answer()

    if not is_admin(update.effective_user.id):
        await query.edit_message_text("Доступ запрещен.")
        return

    data = query.data.replace(ADMIN_PREFIX, "")

    if data == "stats":
        await _admin_stats(update, context)
    elif data == "users":
        await _admin_users(update, context)
    elif data == "subs":
        await _admin_subs(update, context)
    elif data == "payments":
        await _admin_payments(update, context)
    elif data == "shares":
        await _admin_shares(update, context)
    elif data == "pricing":
        await _admin_pricing(update, context)
    elif data == "broadcast":
        await _admin_broadcast_start(update, context)
    elif data == "grant_sub":
        await _admin_grant_sub_start(update, context)
    elif data == "back":
        await admin_command(update, context)


async def _admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show overall statistics."""
    query = update.callback_query

    async with AsyncSessionLocal() as session:
        from app.models import User, Contact, Subscription, ContactShare, Payment

        # Users count
        users_count = (await session.execute(select(func.count(User.id)))).scalar()

        # Contacts count
        contacts_count = (await session.execute(select(func.count(Contact.id)))).scalar()

        # Active subscriptions
        active_subs = (await session.execute(
            select(func.count(Subscription.id)).where(
                Subscription.status == SubscriptionStatus.ACTIVE.value
            )
        )).scalar()

        # Active shares
        active_shares = (await session.execute(
            select(func.count(ContactShare.id)).where(ContactShare.is_active == True)
        )).scalar()

        # Total payments
        from app.models.payment import PaymentStatus as PS
        total_payments = (await session.execute(
            select(func.count(Payment.id)).where(Payment.status == PS.SUCCEEDED.value)
        )).scalar()

        # Revenue (sum)
        from sqlalchemy import cast, Numeric
        revenue = (await session.execute(
            select(func.sum(Payment.amount)).where(
                Payment.status == PS.SUCCEEDED.value,
                Payment.currency == "RUB"
            )
        )).scalar() or 0

    text = (
        f"<b>Статистика</b>\n\n"
        f"Пользователей: {users_count}\n"
        f"Контактов: {contacts_count}\n"
        f"Активных подписок: {active_subs}\n"
        f"Активных публикаций: {active_shares}\n"
        f"Успешных платежей: {total_payments}\n"
        f"Выручка (RUB): {revenue}\n"
        f"\nДата: {datetime.utcnow().strftime('%d.%m.%Y %H:%M UTC')}"
    )

    keyboard = [[InlineKeyboardButton("Назад", callback_data=f"{ADMIN_PREFIX}back")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")


async def _admin_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show recent users."""
    query = update.callback_query

    async with AsyncSessionLocal() as session:
        from app.models import User
        stmt = select(User).order_by(User.created_at.desc()).limit(20)
        result = await session.execute(stmt)
        users = result.scalars().all()

    text = f"<b>Последние пользователи ({len(users)})</b>\n\n"
    for u in users:
        name = escape(u.name or "?")
        tg_id = u.telegram_id
        date = u.created_at.strftime("%d.%m") if u.created_at else "?"
        username = u.profile_data.get("username", "") if u.profile_data else ""
        text += f"- {name} (@{username}) [TG:{tg_id}] {date}\n"

    keyboard = [[InlineKeyboardButton("Назад", callback_data=f"{ADMIN_PREFIX}back")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")


async def _admin_subs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show active subscriptions."""
    query = update.callback_query

    async with AsyncSessionLocal() as session:
        from app.models import Subscription
        stmt = select(Subscription).order_by(Subscription.created_at.desc()).limit(20)
        result = await session.execute(stmt)
        subs = result.scalars().all()

    text = f"<b>Подписки ({len(subs)})</b>\n\n"
    for s in subs:
        end = s.current_period_end.strftime("%d.%m.%Y") if s.current_period_end else "?"
        text += f"- {s.plan} [{s.status}] до {end} ({s.price_amount} {s.price_currency})\n"

    keyboard = [[InlineKeyboardButton("Назад", callback_data=f"{ADMIN_PREFIX}back")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")


async def _admin_payments(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show recent payments."""
    query = update.callback_query

    async with AsyncSessionLocal() as session:
        from app.models import Payment
        stmt = select(Payment).order_by(Payment.created_at.desc()).limit(20)
        result = await session.execute(stmt)
        payments = result.scalars().all()

    text = f"<b>Последние платежи ({len(payments)})</b>\n\n"
    for p in payments:
        date = p.created_at.strftime("%d.%m %H:%M") if p.created_at else "?"
        text += f"- [{p.status}] {p.amount} {p.currency} ({p.provider}) {p.payment_type} {date}\n"

    keyboard = [[InlineKeyboardButton("Назад", callback_data=f"{ADMIN_PREFIX}back")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")


async def _admin_shares(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show active shares."""
    query = update.callback_query

    async with AsyncSessionLocal() as session:
        from app.models import ContactShare
        stmt = select(ContactShare).where(ContactShare.is_active == True).order_by(ContactShare.created_at.desc()).limit(20)
        result = await session.execute(stmt)
        shares = result.scalars().all()

    text = f"<b>Активные публикации ({len(shares)})</b>\n\n"
    for s in shares:
        vis = s.visibility
        price = f"{s.price_amount} {s.price_currency}" if s.price_amount != "0" else "бесплатно"
        views = s.view_count or "0"
        buys = s.purchase_count or "0"
        text += f"- [{vis}] {price} | {views} views, {buys} buys\n"

    keyboard = [[InlineKeyboardButton("Назад", callback_data=f"{ADMIN_PREFIX}back")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")


async def _admin_pricing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show/edit pricing settings."""
    query = update.callback_query

    text = (
        "<b>Настройки цен</b>\n\n"
        f"Подписка Seller: {settings.SUBSCRIPTION_PRICE_RUB} RUB / {settings.SUBSCRIPTION_PRICE_STARS} Stars\n\n"
        "Для изменения цен обновите .env файл:\n"
        "SUBSCRIPTION_PRICE_RUB=990\n"
        "SUBSCRIPTION_PRICE_STARS=500\n\n"
        "И перезапустите бота."
    )

    keyboard = [[InlineKeyboardButton("Назад", callback_data=f"{ADMIN_PREFIX}back")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")


async def _admin_broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start broadcast message flow."""
    query = update.callback_query
    context.user_data["admin_broadcast"] = True

    await query.edit_message_text(
        "Введите текст рассылки (будет отправлен всем пользователям):\n\n"
        "/cancel для отмены"
    )


async def admin_broadcast_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send broadcast message to all users."""
    if not context.user_data.get("admin_broadcast"):
        return False

    if not is_admin(update.effective_user.id):
        return False

    context.user_data.pop("admin_broadcast", None)
    text = update.message.text

    async with AsyncSessionLocal() as session:
        user_service = UserService(session)
        users = await user_service.get_all_users()

        sent = 0
        failed = 0
        for u in users:
            try:
                await context.bot.send_message(chat_id=u.telegram_id, text=text, parse_mode="HTML")
                sent += 1
            except Exception:
                failed += 1

    await update.message.reply_text(f"Рассылка завершена.\nОтправлено: {sent}\nОшибок: {failed}")
    return True


async def _admin_grant_sub_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start grant subscription flow."""
    query = update.callback_query
    context.user_data["admin_grant_sub"] = True

    await query.edit_message_text(
        "Введите Telegram ID пользователя для выдачи подписки:\n\n"
        "/cancel для отмены"
    )


async def admin_grant_sub_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle grant subscription input."""
    if not context.user_data.get("admin_grant_sub"):
        return False

    if not is_admin(update.effective_user.id):
        return False

    context.user_data.pop("admin_grant_sub", None)
    text = update.message.text.strip()

    try:
        telegram_id = int(text)
    except ValueError:
        await update.message.reply_text("Некорректный Telegram ID.")
        return True

    async with AsyncSessionLocal() as session:
        user_service = UserService(session)
        user = await user_service.get_user(telegram_id)

        if not user:
            await update.message.reply_text(f"Пользователь с TG ID {telegram_id} не найден.")
            return True

        sub_service = SubscriptionService(session)
        sub = await sub_service.create_subscription(
            user_id=user.id,
            plan=SubscriptionPlan.SELLER.value,
            provider="admin_grant",
            price_amount=0,
            price_currency="RUB",
        )

        await update.message.reply_text(
            f"Подписка Seller выдана пользователю {user.name} (TG:{telegram_id}).\n"
            f"Действует до: {sub.current_period_end.strftime('%d.%m.%Y')}"
        )

        # Notify the user
        try:
            await context.bot.send_message(
                chat_id=telegram_id,
                text="Вам выдана подписка Seller! Теперь вы можете публиковать контакты для продажи."
            )
        except Exception:
            pass

    return True
