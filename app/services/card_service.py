from app.schemas.profile import UserProfile

class CardService:
    @staticmethod
    def generate_text_card(profile: UserProfile, intro_text: str = None, pitch: str = None) -> str:
        lines = []
        if intro_text:
             lines.append(f"👋 {intro_text}")
             lines.append("")
        
        # Name and basic info
        name = profile.full_name or "Без имени"
        lines.append(f"📇 <b>{name}</b>")
        
        info_line = []
        if profile.job_title:
            info_line.append(profile.job_title)
        if profile.company:
             info_line.append(f"at {profile.company}")
        
        if info_line:
            lines.append(f"💼 {' '.join(info_line)}")
            
        if profile.location:
            lines.append(f"📍 {profile.location}")
            
        lines.append("") # Spacer
        
        if profile.bio:
            lines.append(f"<i>{profile.bio}</i>")
            lines.append("")
        
        if pitch:
            lines.append(f"🚀 <b>Питч</b>: {pitch}")
            lines.append("")

        # One-Pagers removed from text card to keep it clean as per user request
        # if profile.one_pagers: ...

        if profile.interests:
            lines.append(f"⭐ <b>Интересы</b>: {', '.join(profile.interests)}")
            lines.append("")
            
        # Contacts
        contacts = []
        
        # Add Custom Contacts (ignoring legacy phone/email fields for display)
        if profile.custom_contacts:
            for cc in profile.custom_contacts:
                if cc.value.startswith("http") or cc.value.startswith("t.me"):
                     contacts.append(f"• <a href=\"{cc.value}\">{cc.label}</a>")
                else:
                     contacts.append(f"• {cc.label}: {cc.value}")
             
        if contacts:
            lines.append("📞 <b>Контакты</b>:")
            lines.extend(contacts)
            
        return "\n".join(lines)

    @staticmethod
    def generate_vcard_string(profile: UserProfile) -> str:
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
