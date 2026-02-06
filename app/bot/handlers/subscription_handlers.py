"""Handlers for subscription management and payments."""
import logging
from html import escape
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
from telegram.ext import ContextTypes
from app.db.session import AsyncSessionLocal
from app.services.user_service import UserService
from app.services.subscription_service import SubscriptionService
from app.services.payment_service import PaymentService, YooKassaService, TelegramPaymentService
from app.models.subscription import SubscriptionPlan, SubscriptionStatus
from app.models.payment import PaymentType, PaymentProvider, PaymentStatus
from app.core.config import settings

logger = logging.getLogger(__name__)

SUB_PREFIX = "sub_"
PAY_TG_PREFIX = "pay_tg_"
PAY_YOOKASSA_PREFIX = "pay_yookassa_"


async def subscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show subscription options."""
    query = update.callback_query
    if query:
        await query.answer()

    user = update.effective_user

    async with AsyncSessionLocal() as session:
        user_service = UserService(session)
        db_user = await user_service.get_or_create_user(user.id, user.username, user.first_name)

        sub_service = SubscriptionService(session)
        current_sub = await sub_service.get_active_subscription(db_user.id)

        if current_sub and current_sub.status == SubscriptionStatus.ACTIVE.value:
            end_date = current_sub.current_period_end.strftime("%d.%m.%Y") if current_sub.current_period_end else "?"
            text = (
                f"<b>Ваша подписка: {current_sub.plan.upper()}</b>\n\n"
                f"Статус: Активна\n"
                f"Действует до: {end_date}\n"
                f"Оплата: {current_sub.price_amount} {current_sub.price_currency}/мес\n"
            )
            keyboard = [
                [InlineKeyboardButton("Отменить подписку", callback_data=f"{SUB_PREFIX}cancel")],
                [InlineKeyboardButton("Назад", callback_data="menu_main")],
            ]
        else:
            price_rub = settings.SUBSCRIPTION_PRICE_RUB
            price_stars = settings.SUBSCRIPTION_PRICE_STARS
            text = (
                "<b>Подписка Seller</b>\n\n"
                "Что дает подписка:\n"
                "- Публикация контактов для продажи\n"
                "- Настройка видимости полей\n"
                "- Получение оплаты за контакты\n"
                "- Публичный профиль в каталоге\n\n"
                f"Стоимость: <b>{price_rub} RUB/мес</b> или <b>{price_stars} Stars</b>\n"
            )
            keyboard = []

            # Telegram Stars payment
            keyboard.append([InlineKeyboardButton(
                f"Оплатить {price_stars} Stars",
                callback_data=f"{SUB_PREFIX}pay_stars"
            )])

            # YooKassa
            yookassa = YooKassaService()
            if yookassa.is_configured:
                keyboard.append([InlineKeyboardButton(
                    f"Оплатить {price_rub} RUB (карта)",
                    callback_data=f"{SUB_PREFIX}pay_yookassa"
                )])

            keyboard.append([InlineKeyboardButton("Назад", callback_data="menu_main")])

        if query:
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
        else:
            await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")


async def subscription_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle subscription-related callbacks."""
    query = update.callback_query
    await query.answer()

    data = query.data.replace(SUB_PREFIX, "")
    user = update.effective_user

    if data == "pay_stars":
        await _pay_stars_subscription(update, context)
    elif data == "pay_yookassa":
        await _pay_yookassa_subscription(update, context)
    elif data == "cancel":
        await _cancel_subscription(update, context)


async def _pay_stars_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Initiate Telegram Stars payment for subscription."""
    query = update.callback_query
    price_stars = settings.SUBSCRIPTION_PRICE_STARS

    try:
        await context.bot.send_invoice(
            chat_id=update.effective_chat.id,
            title="Подписка Seller",
            description="Месячная подписка на публикацию и продажу контактов",
            payload="subscription_seller_monthly",
            provider_token="",  # Empty for Stars
            currency="XTR",
            prices=[LabeledPrice(label="Подписка Seller (1 мес)", amount=price_stars)],
        )
    except Exception as e:
        logger.exception(f"Error sending Stars invoice: {e}")
        await query.edit_message_text(
            "Ошибка при создании платежа. Попробуйте позже.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Назад", callback_data="menu_main")]]),
        )


async def _pay_yookassa_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Initiate YooKassa payment for subscription."""
    query = update.callback_query
    user = update.effective_user

    yookassa = YooKassaService()
    if not yookassa.is_configured:
        await query.edit_message_text("YooKassa не настроена. Обратитесь к администратору.")
        return

    async with AsyncSessionLocal() as session:
        user_service = UserService(session)
        db_user = await user_service.get_or_create_user(user.id, user.username, user.first_name)

        payment_service = PaymentService(session)
        payment = await payment_service.create_payment(
            user_id=db_user.id,
            payment_type=PaymentType.SUBSCRIPTION.value,
            provider=PaymentProvider.YOOKASSA.value,
            amount=settings.SUBSCRIPTION_PRICE_RUB,
            currency="RUB",
            description="Подписка Seller (1 мес)",
        )

        try:
            yookassa_payment = await yookassa.create_payment(
                amount=settings.SUBSCRIPTION_PRICE_RUB,
                currency="RUB",
                description="Подписка Seller - NetworkBot",
                metadata={
                    "payment_id": str(payment.id),
                    "user_id": str(db_user.id),
                    "type": "subscription",
                },
            )

            confirmation_url = yookassa_payment.get("confirmation", {}).get("confirmation_url", "")
            provider_id = yookassa_payment.get("id", "")

            await payment_service.update_payment_status(
                payment.id,
                PaymentStatus.PENDING.value,
                provider_payment_id=provider_id,
                provider_data=yookassa_payment,
            )

            text = (
                "Для оплаты перейдите по ссылке:\n\n"
                f"{confirmation_url}\n\n"
                "После оплаты подписка активируется автоматически."
            )
            keyboard = [[InlineKeyboardButton("Проверить оплату", callback_data=f"{SUB_PREFIX}check_{payment.id}")]]
            keyboard.append([InlineKeyboardButton("Назад", callback_data="menu_main")])

            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

        except Exception as e:
            logger.exception(f"YooKassa payment error: {e}")
            await payment_service.update_payment_status(payment.id, PaymentStatus.FAILED.value)
            await query.edit_message_text(
                "Ошибка при создании платежа. Попробуйте позже.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Назад", callback_data="menu_main")]]),
            )


async def _cancel_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel the user's subscription."""
    query = update.callback_query
    user = update.effective_user

    async with AsyncSessionLocal() as session:
        user_service = UserService(session)
        db_user = await user_service.get_or_create_user(user.id, user.username, user.first_name)

        sub_service = SubscriptionService(session)
        current_sub = await sub_service.get_active_subscription(db_user.id)

        if current_sub:
            await sub_service.cancel_subscription(current_sub.id)
            end_date = current_sub.current_period_end.strftime("%d.%m.%Y") if current_sub.current_period_end else "?"
            text = (
                "Подписка отменена.\n\n"
                f"Вы можете пользоваться оставшимся периодом до {end_date}.\n"
                "Опубликованные контакты останутся видны до конца периода."
            )
        else:
            text = "У вас нет активной подписки."

        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Главное меню", callback_data="menu_main")]]),
        )


async def handle_pre_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle Telegram pre-checkout query (Stars payment)."""
    pre_checkout = update.pre_checkout_query

    # Always approve (validation happens in successful_payment)
    await pre_checkout.answer(ok=True)


async def handle_successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle successful Telegram payment (Stars)."""
    payment_info = update.message.successful_payment
    user = update.effective_user
    payload = payment_info.invoice_payload

    async with AsyncSessionLocal() as session:
        user_service = UserService(session)
        db_user = await user_service.get_or_create_user(user.id, user.username, user.first_name)

        if payload == "subscription_seller_monthly":
            # Create subscription
            sub_service = SubscriptionService(session)
            sub = await sub_service.create_subscription(
                user_id=db_user.id,
                plan=SubscriptionPlan.SELLER.value,
                provider="telegram_stars",
                price_amount=settings.SUBSCRIPTION_PRICE_STARS,
                price_currency="XTR",
            )

            # Record payment
            payment_service = PaymentService(session)
            await payment_service.create_payment(
                user_id=db_user.id,
                payment_type=PaymentType.SUBSCRIPTION.value,
                provider=PaymentProvider.TELEGRAM.value,
                amount=settings.SUBSCRIPTION_PRICE_STARS,
                currency="XTR",
                description="Подписка Seller через Stars",
                subscription_id=sub.id,
            )

            await update.message.reply_text(
                "Подписка Seller активирована!\n\n"
                "Теперь вы можете публиковать контакты для продажи.\n"
                "Перейдите в раздел /share_contact для начала."
            )

        elif payload.startswith("purchase_"):
            # Contact purchase via Stars
            share_id = payload.replace("purchase_", "")
            from app.services.sharing_service import SharingService
            sharing_service = SharingService(session)

            payment_service = PaymentService(session)
            payment = await payment_service.create_payment(
                user_id=db_user.id,
                payment_type=PaymentType.CONTACT_PURCHASE.value,
                provider=PaymentProvider.TELEGRAM.value,
                amount=payment_info.total_amount,
                currency="XTR",
                description="Покупка контакта через Stars",
                contact_share_id=share_id,
            )

            purchase = await sharing_service.purchase_contact(
                share_id=share_id,
                buyer_id=db_user.id,
                payment_id=payment.id,
                amount_paid=str(payment_info.total_amount),
                currency="XTR",
            )

            await update.message.reply_text(
                "Контакт куплен и добавлен в ваш список!\n"
                "Посмотрите его в /list"
            )


async def pay_telegram_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Initiate Telegram Stars payment for a contact purchase."""
    query = update.callback_query
    await query.answer()

    share_id = query.data.replace(PAY_TG_PREFIX, "")

    async with AsyncSessionLocal() as session:
        from app.services.sharing_service import SharingService
        sharing_service = SharingService(session)
        share = await sharing_service.get_share_by_id(share_id)

        if not share:
            await query.edit_message_text("Контакт не найден.")
            return

        # Convert RUB price to Stars (approximate: 1 Star ~= 2 RUB)
        price_rub = float(share.price_amount or "0")
        price_stars = max(1, int(price_rub / 2))

        try:
            await context.bot.send_invoice(
                chat_id=update.effective_chat.id,
                title="Покупка контакта",
                description=f"Доступ к контакту из каталога",
                payload=f"purchase_{share_id}",
                provider_token="",
                currency="XTR",
                prices=[LabeledPrice(label="Контакт", amount=price_stars)],
            )
        except Exception as e:
            logger.exception(f"Error sending contact invoice: {e}")
            await query.edit_message_text("Ошибка при создании платежа.")


async def pay_yookassa_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Initiate YooKassa payment for a contact purchase."""
    query = update.callback_query
    await query.answer()

    share_id = query.data.replace(PAY_YOOKASSA_PREFIX, "")
    user = update.effective_user

    yookassa = YooKassaService()
    if not yookassa.is_configured:
        await query.edit_message_text("YooKassa не настроена.")
        return

    async with AsyncSessionLocal() as session:
        from app.services.sharing_service import SharingService
        sharing_service = SharingService(session)
        share = await sharing_service.get_share_by_id(share_id)

        if not share:
            await query.edit_message_text("Контакт не найден.")
            return

        user_service = UserService(session)
        db_user = await user_service.get_or_create_user(user.id, user.username, user.first_name)

        price = float(share.price_amount or "0")

        payment_service = PaymentService(session)
        payment = await payment_service.create_payment(
            user_id=db_user.id,
            payment_type=PaymentType.CONTACT_PURCHASE.value,
            provider=PaymentProvider.YOOKASSA.value,
            amount=price,
            currency="RUB",
            description="Покупка контакта",
            contact_share_id=share.id,
        )

        try:
            yookassa_payment = await yookassa.create_payment(
                amount=price,
                currency="RUB",
                description="Покупка контакта - NetworkBot",
                metadata={
                    "payment_id": str(payment.id),
                    "user_id": str(db_user.id),
                    "share_id": str(share.id),
                    "type": "contact_purchase",
                },
            )

            confirmation_url = yookassa_payment.get("confirmation", {}).get("confirmation_url", "")
            provider_id = yookassa_payment.get("id", "")

            await payment_service.update_payment_status(
                payment.id,
                PaymentStatus.PENDING.value,
                provider_payment_id=provider_id,
                provider_data=yookassa_payment,
            )

            text = f"Перейдите по ссылке для оплаты:\n\n{confirmation_url}"
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Назад", callback_data="cmd_browse")],
            ]))

        except Exception as e:
            logger.exception(f"YooKassa contact payment error: {e}")
            await payment_service.update_payment_status(payment.id, PaymentStatus.FAILED.value)
            await query.edit_message_text("Ошибка при создании платежа.")
