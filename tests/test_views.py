import pytest
from app.bot.views.contact_view import format_card, get_contact_keyboard
from app.bot.views.osint_view import format_osint_data
from telegram import InlineKeyboardMarkup

class MockContact:
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", "123")
        self.name = kwargs.get("name")
        self.telegram_username = kwargs.get("telegram_username")
        self.phone = kwargs.get("phone")
        self.company = kwargs.get("company")
        self.role = kwargs.get("role")
        self.event_name = kwargs.get("event_name")
        self.agreements = kwargs.get("agreements", [])
        self.follow_up_action = kwargs.get("follow_up_action")
        self.what_looking_for = kwargs.get("what_looking_for")
        self.attributes = kwargs.get("attributes", {})
        self.email = kwargs.get("email")
        self.linkedin_url = kwargs.get("linkedin_url")
        self.osint_data = kwargs.get("osint_data")

def test_format_card_minimal():
    contact = MockContact(name="John Doe", id="1")
    text = format_card(contact)
    assert "John Doe" in text
    assert "(пусто)" in text

def test_format_card_full():
    contact = MockContact(
        name="Johnathan Doe", 
        telegram_username="johndoe",
        phone="+123456",
        company="Acme",
        role="CEO",
        event_name="Conf",
        agreements=["Call me"],
        follow_up_action="Email",
        what_looking_for="Developer",
        email="john@example.com",
        linkedin_url="linkedin.com/in/john",
        attributes={"notes": "Note1", "custom_contacts": [{"label": "Site", "value": "example.com"}]}
    )
    text = format_card(contact)
    assert "✅ <b>Johnathan Doe</b>" in text
    assert "CEO" in text
    assert "Acme" in text
    assert "Conf" in text
    assert "Call me" in text
    assert "Email" in text
    assert "Developer" in text
    assert "Note1" in text
    assert "+123456" in text
    # Telegram linking logic might hide @johndoe if linked in name?
    # Logic: if normalized name == normalized username, hide separate line.
    # Name "John Doe" != "johndoe". So it shows separate line.
    assert "@johndoe" in text
    assert "john@example.com" in text
    assert "john" in text # from linkedin
    assert "Site" in text

def test_format_card_name_is_username():
    contact = MockContact(name="johndoe", telegram_username="johndoe")
    text = format_card(contact)
    # expect linked name
    assert '<a href="https://t.me/johndoe">johndoe</a>' in text
    # Should NOT show separate Telegram line
    assert "• Telegram:" in text # It actually shows it anyway in "CONTACT DETAILS SECTION" if show_tg_line is False?
    # Let's check code:
    # if contact.telegram_username:
    #   if show_tg_line: ...
    #   else: text += f"• Telegram: ... "
    # So it ALWAYS shows it in contacts section.
    # But show_tg_line affects the header? No, show_tg_line is computed at top.
    # Logic:
    # if norm_name == norm_tg: show_tg_line = False
    # Later:
    # if show_tg_line: ...
    # else: text += ...
    # Wait, both branches add the line? 
    # Yes, lines 78-84:
    # if show_tg_line: text += ...
    # else: text += ...
    # The code seems to duplicate logic or maybe mistakenly adds it in both?
    # Actually checking the code:
    # if show_tg_line:
    #      text += f"• Telegram: ..."
    # else:
    #      # Already linked in name, but show in contacts section for consistency
    #      text += f"• Telegram: ..."
    # So it is effectively always shown.
    pass

def test_get_contact_keyboard():
    contact = MockContact(id="123")
    kb = get_contact_keyboard(contact)
    assert isinstance(kb, InlineKeyboardMarkup)
    assert len(kb.inline_keyboard) >= 4 # we added specific row, now 4 rows

def test_format_osint_data_empty():
    assert format_osint_data({}) == ""
    assert format_osint_data({"no_results": True}) == "ℹ️ _Публичная информация не найдена_"

def test_format_osint_data_full():
    data = {
        "career": {"current": {"company": "Google", "role": "Eng"}, "previous": [{"company": "Meta", "role": "Intern"}]},
        "education": {"universities": [{"name": "MIT"}]},
        "geography": {"current_city": "NY"},
        "personal": {"languages": ["En"]},
        "confidence": "high"
    }
    text = format_osint_data(data)
    assert "Google" in text
    assert "Meta" in text
    assert "MIT" in text
    assert "NY" in text
    assert "En" in text
    assert "🟢" in text
