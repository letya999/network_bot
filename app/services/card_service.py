from app.schemas.profile import UserProfile

class CardService:
    @staticmethod
    def generate_text_card(profile: UserProfile, intro_text: str = None, pitch: str = None, simple_mode: bool = False) -> str:
        """
        Generates a formatted text card for a user profile.

        Args:
            profile: UserProfile object containing user details.
            intro_text: Optional introductory text.
            pitch: Optional pitch text.
            simple_mode: If True, returns a cleaner version without emojis or duplicate info.

        Returns:
            str: The formatted text card.
        """
        from html import escape
        lines = []
        
        if simple_mode:
            # Clean text mode: No emojis, no duplicate profile info
            if intro_text:
                lines.append(escape(intro_text))
            
            if pitch:
                lines.append("")
                # Just the content/link, no label
                lines.append(escape(pitch))
                
            return "\n".join(lines)

        if intro_text:
             lines.append(f"👋 {escape(intro_text)}")
             lines.append("")
        
        # Name and basic info
        name = escape(profile.full_name or "Unnamed")
        lines.append(f"📇 <b>{name}</b>")
        
        info_line = []
        if profile.job_title:
            info_line.append(escape(profile.job_title))
        if profile.company:
             info_line.append(f"at {escape(profile.company)}")
        
        if info_line:
            lines.append(f"💼 {' '.join(info_line)}")
            
        if profile.location:
            lines.append(f"📍 {escape(profile.location)}")
            
        lines.append("") # Spacer
        
        if profile.bio:
            lines.append(f"<i>{escape(profile.bio)}</i>")
            lines.append("")
        
        if pitch:
            lines.append(f"🚀 <b>Pitch</b>: {escape(pitch)}")
            lines.append("")

        # One-Pagers removed from text card to keep it clean as per user request
        # if profile.one_pagers: ...

        if profile.interests:
            lines.append(f"⭐ <b>Interests</b>: {escape(', '.join(profile.interests))}")
            lines.append("")
            
        # Contacts
        contacts = []
        
        # Add Custom Contacts (ignoring legacy phone/email fields for display)
        if profile.custom_contacts:
            for cc in profile.custom_contacts:
                if cc.value.startswith("http") or cc.value.startswith("t.me"):
                     contacts.append(f"• <a href=\"{escape(cc.value)}\">{escape(cc.label)}</a>")
                else:
                     contacts.append(f"• {escape(cc.label)}: {escape(cc.value)}")
             
        if contacts:
            lines.append("📞 <b>Contacts</b>:")
            lines.extend(contacts)
            
        return "\n".join(lines)

    @staticmethod
    def generate_vcard_string(profile: UserProfile) -> str:
        """
        Generates a vCard 3.0 string for the user profile.

        Args:
            profile: UserProfile object.

        Returns:
            str: The vCard string.
        """
        # Simple vCard 3.0 generator
        lines = ["BEGIN:VCARD", "VERSION:3.0"]
        
        name = profile.full_name or "Unknown"
        # Split name if possible (simple split)
        parts = name.split(" ", 1)
        last_name = parts[1] if len(parts) > 1 else ""
        first_name = parts[0]
        
        lines.append(f"N:{last_name};{first_name};;;")
        lines.append(f"FN:{name}")
        
        if profile.company:
            lines.append(f"ORG:{profile.company}")
        if profile.job_title:
            lines.append(f"TITLE:{profile.job_title}")
            
        if profile.phone:
            lines.append(f"TEL;TYPE=CELL:{profile.phone}")
        if profile.email:
            lines.append(f"EMAIL:{profile.email}")
        if profile.website:
            lines.append(f"URL:{profile.website}")
            
        if profile.bio:
            lines.append(f"NOTE:{profile.bio}")
            
        lines.append("END:VCARD")
        return "\n".join(lines)
