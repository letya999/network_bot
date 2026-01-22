import re

def extract_contact_info(text: str) -> dict:
    """
    Extracts contact information (email, phone, linkedin, telegram) from text.
    Returns a dictionary suitable for updating a Contact model.
    """
    data = {}

    # Email
    email_regex = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    email_match = re.search(email_regex, text)
    if email_match:
        data['email'] = email_match.group(0)

    # LinkedIn
    # Captures linkedin.com/in/username or just the full url
    linkedin_regex = r'(https?://)?(www\.)?linkedin\.com/in/[A-Za-z0-9_-]+/?'
    linkedin_match = re.search(linkedin_regex, text)
    if linkedin_match:
        # Ensure it has https://
        url = linkedin_match.group(0)
        if not url.startswith('http'):
            url = 'https://' + url
        data['linkedin_url'] = url

    # Telegram Username (@username)
    # Be careful not to match email addresses as usernames (part before @)
    # But usually email regex catches the whole thing.
    # Telegram usernames are 5-32 chars, a-z, 0-9, underscore.
    tg_username_regex = r'(?<![\w.-])@([a-zA-Z0-9_]{5,32})\b'
    tg_username_match = re.search(tg_username_regex, text)
    if tg_username_match:
        data['telegram_username'] = tg_username_match.group(1) # just the username without @

    # Telegram Link (t.me/username)
    tg_link_regex = r'(https?://)?(www\.)?t\.me/([a-zA-Z0-9_]{5,32})'
    tg_link_match = re.search(tg_link_regex, text)
    if tg_link_match:
        # If we found a link, it overrides/augments the @username search
        data['telegram_username'] = tg_link_match.group(3)

    # Phone Number
    # This is tricky as phone numbers vary wildly.
    # Let's look for international format mostly: + and digits, maybe spaces/dashes.
    # User said "number", could be a local Russian number +7... or 8...
    # Minimal regex: \+?[1-9][0-9 \-\(\)]{7,20}
    # We should exclude things that look like dates or simple integers if possible.
    # A safe bet is looking for + followed by digits.
    phone_regex = r'(?<!\w)(\+?[0-9][0-9\-\(\)\s]{8,20}[0-9])'
    # Filter out common mistakes? 
    # Let's try to be permissive but prioritized.
    # If text is JUST a number, it's likely a phone.
    
    phone_match = re.search(phone_regex, text)
    if phone_match:
        # specific check to avoid things like 2026-01-22
        phone_candidate = phone_match.group(0)
        digits_only = re.sub(r'\D', '', phone_candidate)
        if len(digits_only) >= 7: # Minimum length for a phone number
             data['phone'] = phone_candidate.strip()

    return data
