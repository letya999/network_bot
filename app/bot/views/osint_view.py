"""OSINT view layer - presentation logic for OSINT data formatting."""
from typing import Dict, Any
from datetime import datetime


def format_osint_data(osint_data: Dict[str, Any]) -> str:
    """
    Format OSINT data for display in Telegram.

    Args:
        osint_data: Structured OSINT data dictionary

    Returns:
        Formatted string for Telegram message
    """
    if not osint_data:
        return ""

    if osint_data.get("no_results"):
        return "ℹ️ _Публичная информация не найдена_"

    lines = []

    # Career
    career = osint_data.get("career", {})
    current = career.get("current")
    if current and (current.get("company") or current.get("role")):
        career_str = "💼 *Карьера:*\n"
        role = current.get('role', '')
        company = current.get('company', '')

        if role and company:
            career_str += f"   🚀 {role} @ {company}"
        elif role:
            career_str += f"   🚀 {role}"
        elif company:
            career_str += f"   🏢 {company}"

        if current.get("since"):
            career_str += f" (с {current['since']})"

        if current.get("description"):
             career_str += f"\n   _{current['description'][:50]}..._"

        lines.append(career_str)

    previous = career.get("previous", [])
    if previous:
        # Show all previous jobs found
        for job in previous:
            if job.get("company"):
                role = job.get('role', 'Сотрудник')
                company = job['company']
                job_str = f"   ▫️ {role} @ {company}"

                years = job.get("years")
                if years:
                    job_str += f" ({years})"

                loc = job.get("location")
                if loc:
                    job_str += f" — {loc}"

                lines.append(job_str)

    # Education
    education = osint_data.get("education", {})
    universities = education.get("universities", [])
    if universities:
        edu_str = "\n🎓 *Образование:*\n"
        for uni in universities:
            if uni.get("name"):
                edu_line = f"   🏫 {uni['name']}"
                if uni.get("degree"):
                    edu_line += f" — {uni['degree']}"
                if uni.get("year"):
                    edu_line += f" ({uni['year']})"
                edu_str += edu_line + "\n"
        lines.append(edu_str.rstrip())

    # Certifications/Courses
    courses = education.get("courses", [])
    if courses:
        cert_str = "📜 *Сертификаты:*\n"
        for course in courses[:3]: # Limit to top 3
            if course.get("name"):
                 cert_str += f"   • {course['name']}"
                 if course.get("organization"):
                     cert_str += f" ({course['organization']})"
                 cert_str += "\n"
        lines.append(cert_str.rstrip())

    # Geography & Personal
    geography = osint_data.get("geography", {})
    personal = osint_data.get("personal", {})

    geo_lines = []
    if geography.get("birthplace"):
        geo_lines.append(f"👶 Родом из: {geography['birthplace']}")
    if geography.get("current_city"):
        geo_lines.append(f"📍 Живет в: {geography['current_city']}")
    if geography.get("lived_in"):
        geo_lines.append(f"🌍 Жил в: {', '.join(geography['lived_in'])}")

    if geo_lines:
        lines.append("\n" + "\n".join(geo_lines))

    # Languages & Interests
    if personal.get("languages"):
        lines.append(f"🗣 *Языки:* {', '.join(personal['languages'])}")
    if personal.get("interests"):
        lines.append(f"💡 *Интересы:* {', '.join(personal['interests'][:5])}")
    if personal.get("volunteering"):
         vol_str = "🤝 *Волонтерство:* " + "; ".join(personal["volunteering"][:2])
         lines.append(vol_str)

    # Contacts (if found)
    contacts = osint_data.get("contacts", {})
    contact_lines = []
    if contacts.get("email"):
        contact_lines.append(f"📧 {contacts['email']}")
    if contacts.get("phone"):
        contact_lines.append(f"📞 {contacts['phone']}")
    if contact_lines:
         lines.append("\n" + "\n".join(contact_lines))

    # Social links
    social = osint_data.get("social", {})
    social_links = []
    if social.get("linkedin"):
        social_links.append(f"[LinkedIn]({social['linkedin']})")
    if social.get("twitter"):
        twitter_url = social["twitter"]
        if twitter_url and not twitter_url.startswith("http"):
            twitter_url = f"https://twitter.com/{twitter_url.lstrip('@')}"
        if twitter_url:
             social_links.append(f"[Twitter]({twitter_url})")
    if social.get("github"):
        github_url = social["github"]
        if github_url and not github_url.startswith("http"):
            github_url = f"https://github.com/{github_url}"
        if github_url:
             social_links.append(f"[GitHub]({github_url})")
    if social.get("site"):
         social_links.append(f"[Site]({social['site']})")

    # Add other extracted links if any
    if social.get("other"):
        for i, url in enumerate(social["other"]):
             social_links.append(f"[Link {i+1}]({url})")

    if social_links:
        lines.append(f"\n🔗 *Соцсети:* {' • '.join(social_links)}")

    # Publications
    publications = osint_data.get("publications", [])
    if publications:
        pub_str = "\n📚 *Контент:*\n"
        for pub in publications[:5]:  # Show max 5
            if pub.get("title"):
                pub_type = pub.get("type", "article")
                type_emoji = {"article": "📄", "talk": "🎤", "podcast": "🎙️", "interview": "💬", "code": "💻"}.get(pub_type, "📄")
                if pub.get("url"):
                    pub_str += f"   {type_emoji} [{pub['title'][:40]}...]({pub['url']})\n"
                else:
                    pub_str += f"   {type_emoji} {pub['title'][:50]}\n"
        lines.append(pub_str.rstrip())

    # Confidence indicator
    confidence = osint_data.get("confidence", "")
    if confidence:
        conf_emoji = {"high": "🟢", "medium": "🟡", "low": "🔴"}.get(confidence, "⚪")
        lines.append(f"\n_{conf_emoji} Достоверность: {confidence}_")

    # Enrichment date
    enriched_at = osint_data.get("enriched_at")
    if enriched_at:
        try:
            enriched_date = datetime.fromisoformat(enriched_at)
            lines.append(f"_Обновлено: {enriched_date.strftime('%d.%m.%Y')}_")
        except ValueError:
            pass

    return "\n".join(lines) if lines else ""
