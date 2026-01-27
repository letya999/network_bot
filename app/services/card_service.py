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
        lines.append(f"📇 *{name}*")
        
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
            lines.append(f"_{profile.bio}_")
            lines.append("")
        
        if pitch:
            lines.append(f"🚀 *Питч*: {pitch}")
            lines.append("")

        # Add One-Pagers
        if profile.one_pagers:
            op_lines = []
            for op in profile.one_pagers:
                # Handle both object and legacy string
                content = op.content if hasattr(op, "content") else op
                name = op.name if hasattr(op, "name") else "Ванпейджер"
                
                # If content is a URL, format nicely
                if content.startswith("http"):
                    op_lines.append(f"• [{name}]({content})")
                else:
                    op_lines.append(f"• {name}: {content}")
            
            if op_lines:
                lines.append(f"📄 *Материалы*:")
                lines.extend(op_lines)
                lines.append("")

        if profile.interests:
            lines.append(f"⭐ *Интересы*: {', '.join(profile.interests)}")
            lines.append("")
            
        # Contacts
        contacts = []
        if profile.phone:
            contacts.append(f"📱 {profile.phone}")
        if profile.email:
             contacts.append(f"📧 {profile.email}")
        if profile.telegram:
             contacts.append(f"✈️ {profile.telegram}")
        if profile.website:
             contacts.append(f"🌐 {profile.website}")
             
        if contacts:
            lines.append("📞 *Контакты*:")
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
