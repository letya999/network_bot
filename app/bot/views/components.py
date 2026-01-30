"""Common UI components for Telegram bot interface."""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from typing import List, Optional, Tuple


def create_back_button(callback_data: str = "menu_main", text: str = "🔙 Назад") -> InlineKeyboardButton:
    """
    Create a standard back button.

    Args:
        callback_data: Callback data for the button
        text: Button text (default: "🔙 Назад")

    Returns:
        InlineKeyboardButton instance
    """
    return InlineKeyboardButton(text, callback_data=callback_data)


def create_pagination_keyboard(
    current_page: int,
    total_pages: int,
    prefix: str,
    additional_buttons: Optional[List[List[InlineKeyboardButton]]] = None
) -> InlineKeyboardMarkup:
    """
    Create a pagination keyboard.

    Args:
        current_page: Current page number (0-indexed)
        total_pages: Total number of pages
        prefix: Callback data prefix for pagination buttons (e.g., "list_page_")
        additional_buttons: Additional button rows to append

    Returns:
        InlineKeyboardMarkup with pagination buttons
    """
    keyboard = []

    # Add pagination row if needed
    if total_pages > 1:
        pagination_row = []
        if current_page > 0:
            pagination_row.append(InlineKeyboardButton("◀️", callback_data=f"{prefix}{current_page - 1}"))

        pagination_row.append(InlineKeyboardButton(f"{current_page + 1}/{total_pages}", callback_data="noop"))

        if current_page < total_pages - 1:
            pagination_row.append(InlineKeyboardButton("▶️", callback_data=f"{prefix}{current_page + 1}"))

        keyboard.append(pagination_row)

    # Add additional buttons if provided
    if additional_buttons:
        keyboard.extend(additional_buttons)

    return InlineKeyboardMarkup(keyboard) if keyboard else None


def create_confirmation_keyboard(
    confirm_callback: str,
    cancel_callback: str = "menu_main",
    confirm_text: str = "✅ Да",
    cancel_text: str = "❌ Нет"
) -> InlineKeyboardMarkup:
    """
    Create a confirmation keyboard with Yes/No buttons.

    Args:
        confirm_callback: Callback data for confirm button
        cancel_callback: Callback data for cancel button
        confirm_text: Text for confirm button
        cancel_text: Text for cancel button

    Returns:
        InlineKeyboardMarkup with confirmation buttons
    """
    keyboard = [
        [
            InlineKeyboardButton(confirm_text, callback_data=confirm_callback),
            InlineKeyboardButton(cancel_text, callback_data=cancel_callback)
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def create_menu_keyboard(
    items: List[Tuple[str, str]],
    columns: int = 2,
    back_button: bool = True,
    back_callback: str = "menu_main"
) -> InlineKeyboardMarkup:
    """
    Create a generic menu keyboard with items arranged in columns.

    Args:
        items: List of (text, callback_data) tuples
        columns: Number of columns to arrange buttons in
        back_button: Whether to add a back button
        back_callback: Callback data for back button

    Returns:
        InlineKeyboardMarkup with menu buttons
    """
    keyboard = []

    # Arrange items in rows
    for i in range(0, len(items), columns):
        row = [InlineKeyboardButton(text, callback_data=callback) for text, callback in items[i:i + columns]]
        keyboard.append(row)

    # Add back button if requested
    if back_button:
        keyboard.append([create_back_button(back_callback)])

    return InlineKeyboardMarkup(keyboard) if keyboard else None
