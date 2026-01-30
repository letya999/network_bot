"""View layer package - presentation logic for the bot."""
from app.bot.views.contact_view import format_card, get_contact_keyboard
from app.bot.views.osint_view import format_osint_data
from app.bot.views.components import (
    create_back_button,
    create_pagination_keyboard,
    create_confirmation_keyboard,
    create_menu_keyboard
)

__all__ = [
    'format_card',
    'get_contact_keyboard',
    'format_osint_data',
    'create_back_button',
    'create_pagination_keyboard',
    'create_confirmation_keyboard',
    'create_menu_keyboard'
]
