"""Handlers for contact sharing, marketplace, and purchasing."""
import logging
from html import escape
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from app.db.session import AsyncSessionLocal
from app.services.user_service import UserService
from app.services.contact_service import ContactService
from app.services.sharing_service import SharingService, DEFAULT_VISIBLE_FIELDS, ALL_SHAREABLE_FIELDS, CONTACT_FIELDS, PROFILE_FIELDS
from app.services.subscription_service import SubscriptionService
from app.models.contact_share import ShareVisibility

logger = logging.getLogger(__name__)

# Callback prefixes
SHARE_PREFIX = "share_"
SHARE_CONTACT_PREFIX = "share_contact_"
SHARE_VIS_PREFIX = "share_vis_"
SHARE_FIELD_PREFIX = "share_field_"
SHARE_PRICE_PREFIX = "share_price_"
SHARE_CONFIRM_PREFIX = "share_confirm_"
SHARE_TOGGLE_PREFIX = "share_toggle_"
SHARE_UNSHARE_PREFIX = "share_unshare_"
BROWSE_PREFIX = "browse_"
BROWSE_VIEW_PREFIX = "browse_view_"
BUY_PREFIX = "buy_"
MY_SHARES_PREFIX = "my_shares_"
MY_PURCHASES_PREFIX = "my_purchases_"


async def share_contact_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start sharing a contact - show list of contacts to share."""
    query = update.callback_query
    if query:
        await query.answer()

    user = update.effective_user

    async with AsyncSessionLocal() as session:
        user_service = UserService(session)
        db_user = await user_service.get_or_create_user(user.id, user.username, user.first_name)

        # Check subscription
        sub_service = SubscriptionService(session)
        has_access = await sub_service.has_seller_access(db_user.id)

        if not has_access:
            text = (
                "Для публикации контактов нужна подписка Seller.\n\n"
                "Подписка позволяет:\n"
                "- Публиковать контакты для продажи\n"
                "- Настраивать видимость полей\n"
                "- Получать оплату за контакты\n\n"
                "Оформите подписку в разделе /subscribe"
            )
            if query:
                await query.edit_message_text(text)
            else:
                await update.message.reply_text(text)
            return

        contact_service = ContactService(session)
        contacts = await contact_service.get_recent_contacts(db_user.id, limit=20)

        if not contacts:
            text = "У вас пока нет контактов для публикации."
            if query:
                await query.edit_message_text(text)
            else:
                await update.message.reply_text(text)
            return

        text = "Выберите контакт для публикации:"
        keyboard = []
        for c in contacts:
            label = c.name or "Без имени"
            if c.company:
                label += f" ({c.company})"
            keyboard.append([InlineKeyboardButton(
                label, callback_data=f"{SHARE_CONTACT_PREFIX}{c.id}"
            )])
        keyboard.append([InlineKeyboardButton("Назад", callback_data="menu_main")])

        markup = InlineKeyboardMarkup(keyboard)
        if query:
            await query.edit_message_text(text, reply_markup=markup)
        else:
            await update.message.reply_text(text, reply_markup=markup)


async def share_contact_setup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set up sharing options for selected contact."""
    query = update.callback_query
    await query.answer()

    contact_id = query.data.replace(SHARE_CONTACT_PREFIX, "")
    context.user_data["sharing_contact_id"] = contact_id
    context.user_data["share_visible_fields"] = list(DEFAULT_VISIBLE_FIELDS)
    context.user_data["share_visibility"] = ShareVisibility.PUBLIC.value
    context.user_data["share_price"] = "0"

    await _show_share_setup(update, context, contact_id)


async def _show_share_setup(update: Update, context: ContextTypes.DEFAULT_TYPE, contact_id: str):
    """Show the sharing configuration menu."""
    query = update.callback_query
    visible_fields = context.user_data.get("share_visible_fields", DEFAULT_VISIBLE_FIELDS)
    visibility = context.user_data.get("share_visibility", ShareVisibility.PUBLIC.value)
    price = context.user_data.get("share_price", "0")

    vis_labels = {
        ShareVisibility.PUBLIC.value: "Публичный",
        ShareVisibility.PRIVATE.value: "Приватный",
        ShareVisibility.PAID.value: "Платный",
    }

    async with AsyncSessionLocal() as session:
        contact_service = ContactService(session)
        contact = await contact_service.get_contact_by_id(contact_id)
        name = escape(contact.name) if contact else "Контакт"

    text = (
        f"<b>Настройка публикации: {name}</b>\n\n"
        f"Видимость: <b>{vis_labels.get(visibility, visibility)}</b>\n"
    )
    if visibility == ShareVisibility.PAID.value:
        text += f"Цена: <b>{price} RUB</b>\n"

    text += f"\nВидимые поля ({len(visible_fields)}):\n"
    for f in visible_fields:
        label = PROFILE_FIELDS.get(f, CONTACT_FIELDS.get(f, f))
        text += f"  + {label}\n"

    keyboard = [
        [InlineKeyboardButton(
            f"Видимость: {vis_labels.get(visibility, visibility)}",
            callback_data=f"{SHARE_VIS_PREFIX}cycle"
        )],
        [InlineKeyboardButton(
            "Настроить видимые поля",
            callback_data=f"{SHARE_FIELD_PREFIX}menu"
        )],
    ]

    if visibility == ShareVisibility.PAID.value:
        keyboard.append([InlineKeyboardButton(
            f"Цена: {price} RUB",
            callback_data=f"{SHARE_PRICE_PREFIX}set"
        )])

    keyboard.append([InlineKeyboardButton(
        "Опубликовать", callback_data=f"{SHARE_CONFIRM_PREFIX}{contact_id}"
    )])
    keyboard.append([InlineKeyboardButton("Отмена", callback_data="menu_main")])

    await query.edit_message_text(
        text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML"
    )


async def share_visibility_cycle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cycle through visibility options."""
    query = update.callback_query
    await query.answer()

    current = context.user_data.get("share_visibility", ShareVisibility.PUBLIC.value)
    cycle = [ShareVisibility.PUBLIC.value, ShareVisibility.PRIVATE.value, ShareVisibility.PAID.value]
    idx = cycle.index(current) if current in cycle else 0
    next_vis = cycle[(idx + 1) % len(cycle)]
    context.user_data["share_visibility"] = next_vis

    contact_id = context.user_data.get("sharing_contact_id")
    await _show_share_setup(update, context, contact_id)


async def share_fields_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show toggleable field list."""
    query = update.callback_query
    await query.answer()

    visible = set(context.user_data.get("share_visible_fields", DEFAULT_VISIBLE_FIELDS))

    keyboard = []
    all_fields = {**PROFILE_FIELDS, **CONTACT_FIELDS}
    for field, label in all_fields.items():
        icon = "+" if field in visible else "-"
        keyboard.append([InlineKeyboardButton(
            f"{icon} {label}",
            callback_data=f"{SHARE_TOGGLE_PREFIX}{field}"
        )])

    keyboard.append([InlineKeyboardButton("Готово", callback_data=f"{SHARE_CONTACT_PREFIX}{context.user_data.get('sharing_contact_id')}")])

    await query.edit_message_text(
        "Выберите поля для отображения:\n(+ видно, - скрыто)",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def share_toggle_field(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toggle a field's visibility."""
    query = update.callback_query
    await query.answer()

    field = query.data.replace(SHARE_TOGGLE_PREFIX, "")
    visible = set(context.user_data.get("share_visible_fields", DEFAULT_VISIBLE_FIELDS))

    if field in visible:
        visible.discard(field)
        # Name is always visible
        if field == "name":
            visible.add("name")
    else:
        visible.add(field)

    context.user_data["share_visible_fields"] = list(visible)
    await share_fields_menu(update, context)


async def share_price_set(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set price for paid sharing."""
    query = update.callback_query
    await query.answer()

    context.user_data["awaiting_share_price"] = True
    await query.edit_message_text(
        "Введите цену в рублях (например: 500):\n\n"
        "Отправьте /cancel для отмены"
    )


async def share_price_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle price input text."""
    if not context.user_data.get("awaiting_share_price"):
        return False

    text = update.message.text.strip()
    try:
        price = int(text)
        if price < 0:
            raise ValueError
        context.user_data["share_price"] = str(price)
        context.user_data.pop("awaiting_share_price", None)
        await update.message.reply_text(f"Цена установлена: {price} RUB")
        return True
    except ValueError:
        await update.message.reply_text("Введите корректное число (целое, >= 0)")
        return True


async def share_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Confirm and create the share."""
    query = update.callback_query
    await query.answer()

    contact_id = query.data.replace(SHARE_CONFIRM_PREFIX, "")
    user = update.effective_user

    async with AsyncSessionLocal() as session:
        user_service = UserService(session)
        db_user = await user_service.get_or_create_user(user.id, user.username, user.first_name)

        sharing_service = SharingService(session)
        share = await sharing_service.share_contact(
            owner_id=db_user.id,
            contact_id=contact_id,
            visibility=context.user_data.get("share_visibility", ShareVisibility.PUBLIC.value),
            visible_fields=context.user_data.get("share_visible_fields", DEFAULT_VISIBLE_FIELDS),
            price_amount=context.user_data.get("share_price", "0"),
        )

        bot_username = (await context.bot.get_me()).username
        share_link = f"https://t.me/{bot_username}?start=share_{share.share_token}"

        text = (
            f"<b>Контакт опубликован!</b>\n\n"
            f"Ссылка для просмотра:\n{share_link}\n\n"
            f"Отправьте эту ссылку тем, кому хотите показать контакт."
        )

        keyboard = [[InlineKeyboardButton("Мои публикации", callback_data="cmd_my_shares")]]
        keyboard.append([InlineKeyboardButton("Главное меню", callback_data="menu_main")])

        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")

    # Cleanup
    for k in ["sharing_contact_id", "share_visible_fields", "share_visibility", "share_price"]:
        context.user_data.pop(k, None)


async def my_shares(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user's shared contacts."""
    query = update.callback_query
    if query:
        await query.answer()

    user = update.effective_user

    async with AsyncSessionLocal() as session:
        user_service = UserService(session)
        db_user = await user_service.get_or_create_user(user.id, user.username, user.first_name)

        sharing_service = SharingService(session)
        shares = await sharing_service.get_user_shares(db_user.id)

        if not shares:
            text = "У вас пока нет опубликованных контактов."
            if query:
                await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Опубликовать контакт", callback_data="cmd_share_contact")],
                    [InlineKeyboardButton("Назад", callback_data="menu_main")],
                ]))
            else:
                await update.message.reply_text(text)
            return

        text = f"<b>Мои публикации ({len(shares)})</b>\n\n"
        keyboard = []
        for s in shares:
            # Load contact name
            contact_service = ContactService(session)
            contact = await contact_service.get_contact_by_id(s.contact_id)
            name = escape(contact.name) if contact else "?"

            vis = {"public": "Pub", "private": "Priv", "paid": f"{s.price_amount}R"}.get(s.visibility, "?")
            keyboard.append([
                InlineKeyboardButton(f"{name} [{vis}]", callback_data=f"browse_view_{s.id}"),
                InlineKeyboardButton("X", callback_data=f"{SHARE_UNSHARE_PREFIX}{s.id}"),
            ])

        keyboard.append([InlineKeyboardButton("Опубликовать ещё", callback_data="cmd_share_contact")])
        keyboard.append([InlineKeyboardButton("Назад", callback_data="menu_main")])

        if query:
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
        else:
            await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")


async def unshare_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Unshare (deactivate) a contact share."""
    query = update.callback_query
    await query.answer()

    share_id = query.data.replace(SHARE_UNSHARE_PREFIX, "")

    async with AsyncSessionLocal() as session:
        sharing_service = SharingService(session)
        await sharing_service.unshare_contact(share_id)

    await query.edit_message_text("Публикация отключена.")
    await my_shares(update, context)


async def browse_contacts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Browse public/paid shared contacts (marketplace)."""
    query = update.callback_query
    if query:
        await query.answer()

    async with AsyncSessionLocal() as session:
        sharing_service = SharingService(session)
        shares = await sharing_service.get_public_shares(limit=20)

        if not shares:
            text = "Пока нет доступных контактов."
            if query:
                await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Назад", callback_data="menu_main")]
                ]))
            else:
                await update.message.reply_text(text)
            return

        text = "<b>Каталог контактов</b>\n\nДоступные для просмотра/покупки:\n"
        keyboard = []
        for s in shares:
            contact_service = ContactService(session)
            contact = await contact_service.get_contact_by_id(s.contact_id)
            if not contact:
                continue

            label = contact.name or "Без имени"
            if contact.company:
                label += f" ({contact.company})"

            price_label = ""
            if s.visibility == ShareVisibility.PAID.value and s.price_amount != "0":
                price_label = f" - {s.price_amount} RUB"
            else:
                price_label = " - Free"

            keyboard.append([InlineKeyboardButton(
                f"{label}{price_label}",
                callback_data=f"{BROWSE_VIEW_PREFIX}{s.id}"
            )])

        keyboard.append([InlineKeyboardButton("Назад", callback_data="menu_main")])

        if query:
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
        else:
            await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")


async def browse_view_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """View a shared contact's public info."""
    query = update.callback_query
    await query.answer()

    share_id = query.data.replace(BROWSE_VIEW_PREFIX, "")
    user = update.effective_user

    async with AsyncSessionLocal() as session:
        user_service = UserService(session)
        db_user = await user_service.get_or_create_user(user.id, user.username, user.first_name)

        sharing_service = SharingService(session)
        share = await sharing_service.get_share_by_id(share_id)

        if not share or not share.is_active:
            await query.edit_message_text("Контакт больше недоступен.")
            return

        contact_service = ContactService(session)
        contact = await contact_service.get_contact_by_id(share.contact_id)
        if not contact:
            await query.edit_message_text("Контакт не найден.")
            return

        # Check if already purchased
        already_purchased = await sharing_service.has_purchased(share.id, db_user.id)
        is_owner = share.owner_id == db_user.id

        # Get filtered data
        if already_purchased or is_owner:
            data = await sharing_service.get_filtered_contact_data(share, contact)
        elif share.visibility == ShareVisibility.PAID.value:
            # Show only basic info (name, company, role)
            data = {}
            for f in ["name", "company", "role", "what_looking_for"]:
                if f in (share.visible_fields or []):
                    val = getattr(contact, f, None)
                    if val:
                        data[f] = val
        else:
            data = await sharing_service.get_filtered_contact_data(share, contact)

        # Get seller info
        seller_service = UserService(session)
        seller = await seller_service.get_user(share.owner.telegram_id if hasattr(share, 'owner') and share.owner else None)

        # Build display text
        text = f"<b>{escape(data.get('name', 'Без имени'))}</b>\n"

        if data.get("company"):
            text += f"Компания: {escape(data['company'])}\n"
        if data.get("role"):
            text += f"Роль: {escape(data['role'])}\n"
        if data.get("what_looking_for"):
            text += f"\nИщет: {escape(data['what_looking_for'])}\n"
        if data.get("can_help_with"):
            text += f"Может помочь: {escape(data['can_help_with'])}\n"

        # Contact details (only if purchased or free)
        if already_purchased or is_owner or share.visibility == ShareVisibility.PUBLIC.value:
            if data.get("phone"):
                text += f"\nТелефон: {escape(data['phone'])}\n"
            if data.get("email"):
                text += f"Email: {escape(data['email'])}\n"
            if data.get("telegram_username"):
                tg = data['telegram_username'].lstrip("@")
                text += f"Telegram: @{escape(tg)}\n"
            if data.get("linkedin_url"):
                text += f"LinkedIn: {escape(data['linkedin_url'])}\n"

        if share.description:
            text += f"\n<i>{escape(share.description)}</i>\n"

        # Update view count
        current_views = int(share.view_count or "0")
        share.view_count = str(current_views + 1)
        await session.commit()

        # Build keyboard
        keyboard = []
        if share.visibility == ShareVisibility.PAID.value and not already_purchased and not is_owner:
            price = share.price_amount or "0"
            keyboard.append([InlineKeyboardButton(
                f"Купить за {price} RUB",
                callback_data=f"{BUY_PREFIX}{share.id}"
            )])

        if (share.visibility == ShareVisibility.PUBLIC.value or already_purchased) and not is_owner:
            keyboard.append([InlineKeyboardButton(
                "Добавить в мои контакты",
                callback_data=f"{BUY_PREFIX}free_{share.id}"
            )])

        if already_purchased:
            text += "\n<i>Вы уже приобрели этот контакт</i>\n"

        keyboard.append([InlineKeyboardButton("Назад к каталогу", callback_data="cmd_browse")])
        keyboard.append([InlineKeyboardButton("Главное меню", callback_data="menu_main")])

        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")


async def buy_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Buy/acquire a shared contact."""
    query = update.callback_query
    await query.answer()

    data = query.data.replace(BUY_PREFIX, "")
    is_free = data.startswith("free_")
    share_id = data.replace("free_", "") if is_free else data

    user = update.effective_user

    async with AsyncSessionLocal() as session:
        user_service = UserService(session)
        db_user = await user_service.get_or_create_user(user.id, user.username, user.first_name)

        sharing_service = SharingService(session)
        share = await sharing_service.get_share_by_id(share_id)

        if not share or not share.is_active:
            await query.edit_message_text("Контакт больше недоступен.")
            return

        # Check if already purchased
        if await sharing_service.has_purchased(share.id, db_user.id):
            await query.edit_message_text("Вы уже приобрели этот контакт.")
            return

        if is_free or share.visibility == ShareVisibility.PUBLIC.value or share.price_amount == "0":
            # Free acquisition
            purchase = await sharing_service.purchase_contact(
                share_id=share.id,
                buyer_id=db_user.id,
                amount_paid="0",
                currency="RUB",
            )

            text = (
                "Контакт добавлен в ваш список!\n\n"
                "Посмотрите его в разделе /list"
            )
            keyboard = [
                [InlineKeyboardButton("Мои контакты", callback_data="cmd_list")],
                [InlineKeyboardButton("Каталог", callback_data="cmd_browse")],
            ]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            # Paid - initiate payment
            price = float(share.price_amount or "0")
            context.user_data["pending_purchase_share_id"] = str(share.id)
            context.user_data["pending_purchase_amount"] = price

            text = (
                f"Для покупки контакта нужно оплатить {share.price_amount} RUB.\n\n"
                "Выберите способ оплаты:"
            )
            keyboard = [
                [InlineKeyboardButton(
                    "Telegram Stars",
                    callback_data=f"pay_tg_{share.id}"
                )],
                [InlineKeyboardButton(
                    "YooKassa (карта)",
                    callback_data=f"pay_yookassa_{share.id}"
                )],
                [InlineKeyboardButton("Отмена", callback_data="cmd_browse")],
            ]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def handle_deep_link_share(update: Update, context: ContextTypes.DEFAULT_TYPE, token: str):
    """Handle deep link: /start share_<token>."""
    user = update.effective_user

    async with AsyncSessionLocal() as session:
        sharing_service = SharingService(session)
        share = await sharing_service.get_share_by_token(token)

        if not share or not share.is_active:
            await update.message.reply_text("Ссылка на контакт недействительна или устарела.")
            return

        # Redirect to browse view
        user_service = UserService(session)
        db_user = await user_service.get_or_create_user(user.id, user.username, user.first_name)

        contact_service = ContactService(session)
        contact = await contact_service.get_contact_by_id(share.contact_id)
        if not contact:
            await update.message.reply_text("Контакт не найден.")
            return

        already_purchased = await sharing_service.has_purchased(share.id, db_user.id)
        is_owner = share.owner_id == db_user.id

        # Get filtered data
        if already_purchased or is_owner or share.visibility == ShareVisibility.PUBLIC.value:
            data = await sharing_service.get_filtered_contact_data(share, contact)
        else:
            data = {"name": contact.name, "company": contact.company, "role": contact.role}

        text = f"<b>{escape(data.get('name', 'Без имени'))}</b>\n"
        if data.get("company"):
            text += f"Компания: {escape(data['company'])}\n"
        if data.get("role"):
            text += f"Роль: {escape(data['role'])}\n"

        if already_purchased or is_owner or share.visibility == ShareVisibility.PUBLIC.value:
            if data.get("phone"):
                text += f"\nТелефон: {escape(data['phone'])}\n"
            if data.get("email"):
                text += f"Email: {escape(data['email'])}\n"
            if data.get("telegram_username"):
                tg = data["telegram_username"].lstrip("@")
                text += f"Telegram: @{escape(tg)}\n"

        keyboard = []
        if share.visibility == ShareVisibility.PAID.value and not already_purchased and not is_owner:
            keyboard.append([InlineKeyboardButton(
                f"Купить за {share.price_amount} RUB",
                callback_data=f"{BUY_PREFIX}{share.id}"
            )])
        elif not already_purchased and not is_owner:
            keyboard.append([InlineKeyboardButton(
                "Добавить в мои контакты",
                callback_data=f"{BUY_PREFIX}free_{share.id}"
            )])

        if already_purchased:
            text += "\n<i>Вы уже приобрели этот контакт</i>"

        keyboard.append([InlineKeyboardButton("Каталог", callback_data="cmd_browse")])
        keyboard.append([InlineKeyboardButton("Главное меню", callback_data="menu_main")])

        await update.message.reply_text(
            text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML"
        )


async def my_purchases(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user's purchased contacts."""
    query = update.callback_query
    if query:
        await query.answer()

    user = update.effective_user

    async with AsyncSessionLocal() as session:
        user_service = UserService(session)
        db_user = await user_service.get_or_create_user(user.id, user.username, user.first_name)

        sharing_service = SharingService(session)
        purchases = await sharing_service.get_user_purchases(db_user.id)

        if not purchases:
            text = "Вы пока не приобрели ни одного контакта."
            if query:
                await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Каталог", callback_data="cmd_browse")],
                    [InlineKeyboardButton("Назад", callback_data="menu_main")],
                ]))
            else:
                await update.message.reply_text(text)
            return

        text = f"<b>Мои покупки ({len(purchases)})</b>\n\n"
        keyboard = []
        for p in purchases:
            contact_service = ContactService(session)
            if p.copied_contact_id:
                contact = await contact_service.get_contact_by_id(p.copied_contact_id)
                label = contact.name if contact else "?"
            else:
                label = "Контакт"

            price_label = f" ({p.amount_paid} {p.currency})" if p.amount_paid != "0" else " (бесплатно)"
            keyboard.append([InlineKeyboardButton(
                f"{label}{price_label}",
                callback_data=f"contact_view_{p.copied_contact_id}" if p.copied_contact_id else "cmd_browse"
            )])

        keyboard.append([InlineKeyboardButton("Назад", callback_data="menu_main")])

        if query:
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
        else:
            await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
