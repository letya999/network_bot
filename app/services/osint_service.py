"""
OSINT & Enrichment Service

Enriches contacts with publicly available information from:
- Google Custom Search (LinkedIn profiles, publications, talks)
- Gemini AI for structuring found data
"""

import logging
import asyncio
import aiohttp
import json
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from urllib.parse import quote_plus
import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.core.config import settings
from app.models.contact import Contact
from app.services.gemini_service import GeminiService
from app.config.constants import (
    UNKNOWN_CONTACT_NAME,
    OSINT_ENRICHMENT_DELAY_DAYS,
    TAVILY_MAX_RESULTS,
    TAVILY_SEARCH_DEPTH,
    TAVILY_TIMEOUT_SECONDS,
    BATCH_ENRICHMENT_DELAY_SECONDS
)

logger = logging.getLogger(__name__)


class OSINTService:
    """Service for enriching contacts with OSINT data."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.gemini = GeminiService()

    async def _tavily_search(self, query: str, include_domains: List[str] = None) -> List[Dict[str, Any]]:
        """
        Perform a search using Tavily AI API.
        Returns rich results with content.
        """
        if not settings.TAVILY_API_KEY:
            logger.warning("Tavily API key not configured")
            return []

        url = "https://api.tavily.com/search"
        payload = {
            "api_key": settings.TAVILY_API_KEY,
            "query": query,
            "search_depth": TAVILY_SEARCH_DEPTH,  # "basic" or "advanced"
            "include_answer": False,
            "include_raw_content": False,
            "max_results": TAVILY_MAX_RESULTS,
        }
        
        if include_domains:
            payload["include_domains"] = include_domains

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=TAVILY_TIMEOUT_SECONDS)) as response:
                    if response.status != 200:
                        logger.error(f"Tavily error {response.status}: {await response.text()}")
                        return []
                    
                    data = await response.json()
                    return data.get("results", [])

        except Exception:
            logger.exception("Tavily search error")
            return []

    async def _structure_osint_data(self, raw_data: Dict[str, Any], contact_info: Dict[str, str]) -> Dict[str, Any]:
        """
        Use Gemini to structure the raw OSINT data.

        Args:
            raw_data: Raw search results from various sources
            contact_info: Basic contact information (name, company, etc.)

        Returns:
            Structured OSINT data dictionary
        """
        if not self.gemini.model:
            logger.warning("Gemini not configured - returning raw data")
            return {"raw_results": raw_data, "enriched_at": datetime.now().isoformat()}

        prompt = self.gemini.get_prompt("enrich_osint")
        if not prompt:
            logger.warning("OSINT prompt not found - using default")
            prompt = self._get_default_osint_prompt()

        # The input data format depends on what enrich_contact passes.
        # In the new Tavily flow, we pass a specific dict.
        # We'll just pass whatever raw_data is directly to the prompt as "Input Data".
        
        try:
            response = await self.gemini.model.generate_content_async(
                f"{prompt}\n\nInput Data:\n{json.dumps(raw_data, ensure_ascii=False)}",
                generation_config={
                    "response_mime_type": "application/json"
                }
            )

            json_str = response.text.strip()
            if json_str.startswith("```json"):
                json_str = json_str[7:]
            if json_str.startswith("```"):
                json_str = json_str[3:]
            if json_str.endswith("```"):
                json_str = json_str[:-3]

            structured = json.loads(json_str)
            structured["enriched_at"] = datetime.now().isoformat()
            return structured

        except Exception as e:
            logger.exception("Error structuring OSINT data")
            return {
                "raw_results": raw_data,
                "enriched_at": datetime.now().isoformat(),
                "error": str(e)
            }

    def _get_default_osint_prompt(self) -> str:
        """Return default OSINT structuring prompt."""
        return """
Analyze the search results and extract structured information about the person.

Return a JSON object with these fields:

{
  "career": {
    "current": {"company": string, "role": string, "since": string or null},
    "previous": [{"company": string, "role": string, "years": string}]
  },
  "education": {
    "universities": [{"name": string, "degree": string or null, "year": number or null}],
    "courses": [{"name": string, "year": number or null}]
  },
  "geography": {
    "current_city": string or null,
    "lived_in": [string]
  },
  "publications": [
    {"type": "article|talk|podcast|interview", "title": string, "url": string or null}
  ],
  "social": {
    "linkedin": string or null,
    "twitter": string or null,
    "github": string or null,
    "facebook": string or null
  },
  "confidence": "high" | "medium" | "low"
}

Only include information you are confident about based on the search results.
If you cannot find information for a field, use null or empty array.
For confidence: "high" if multiple sources confirm the data, "medium" if found in one reliable source, "low" if uncertain.
"""

    async def search_potential_profiles(self, contact_id: uuid.UUID) -> List[Dict[str, str]]:
        """
        Step 1: Search for potential LinkedIn profiles.
        Returns a list of candidates {name, title, url}
        """
        # Get contact
        result = await self.session.execute(
            select(Contact).where(Contact.id == contact_id)
        )
        contact = result.scalar_one_or_none()
        if not contact:
            return []

        logger.info(f"Searching profiles for {contact.name}")
        
        # Search query focused on finding the profile
        query = f"{contact.name} {contact.company or ''} {contact.role or ''} linkedin"
        results = await self._tavily_search(query)
        
        candidates = []
        seen_urls = set()
        
        for search_result in results:
            url = search_result.get("url", "")
            if "linkedin.com/in/" in url and url not in seen_urls:
                seen_urls.add(url)
                # Clean up title for display
                title = search_result.get("title", "").replace(" | LinkedIn", "").replace(" - LinkedIn", "")
                candidates.append({
                    "name": title,  # Usually "Name - Role"
                    "url": url,
                    "snippet": search_result.get("content", "")[:100]
                })
        
        return candidates

    async def enrich_contact_final(
        self,
        contact_id: uuid.UUID,
        linkedin_url: str
    ) -> Dict[str, Any]:
        """
        Step 2: Deep enrich using the specific confirmed URL.
        """
        result = await self.session.execute(
            select(Contact).where(Contact.id == contact_id)
        )
        contact = result.scalar_one_or_none()
        if not contact:
            return {"status": "error", "message": "Contact not found"}

        logger.info(f"Deep enriching {contact.name} with URL {linkedin_url}")

        # Parallelize API calls for better performance
        # 1. Get specifically the profile content (Tavily reads the page)
        # 2. Get broader context (articles, etc)
        content_query = f"{contact.name} {contact.company or ''} interview podcast talk article"
        
        # Execute both searches in parallel
        profile_results, content_results = await asyncio.gather(
            self._tavily_search(linkedin_url),
            self._tavily_search(content_query),
            return_exceptions=True  # Continue if one fails
        )
        
        # Handle potential exceptions
        all_results = []
        if not isinstance(profile_results, Exception):
            all_results.extend(profile_results)
        else:
            logger.error(f"Profile search failed: {profile_results}")
            
        if not isinstance(content_results, Exception):
            all_results.extend(content_results)
        else:
            logger.error(f"Content search failed: {content_results}")

        
        # Structure with Gemini
        contact_info = {
            "name": contact.name,
            "company": contact.company,
            "role": contact.role,
        }

        prompt_input = {
            "contact": contact_info,
            "linkedin_profile": linkedin_url,
            "search_results": [
                {
                    "title": result.get("title"),
                    "url": result.get("url"),
                    "content": result.get("content", "")[:1500] # Increase context slightly for the main profile
                } for result in all_results
            ]
        }

        structured_data = await self._structure_osint_data(prompt_input, contact_info)

        # Update Contact
        contact.osint_data = structured_data
        contact.linkedin_url = linkedin_url # Confirm the URL
        
        await self.session.commit()
        await self.session.refresh(contact)

        return {
            "status": "success",
            "data": structured_data
        }
    
    async def enrich_contact(self, contact_id: uuid.UUID, force: bool = False) -> Dict[str, Any]:
        """
        Orchestrate the enrichment process (Auto-mode).
        1. Search for profiles.
        2. Pick the best candidate.
        3. Enrich.
        """
        # Check cache
        if not force:
            result = await self.session.execute(
                select(Contact).where(Contact.id == contact_id)
            )
            contact = result.scalar_one_or_none()
            if not contact:
                 return {"status": "error", "message": "Contact not found"}
            
            if contact.name == UNKNOWN_CONTACT_NAME:
                return {"status": "error", "message": "Contact name is required"}
                 
            if contact.osint_data and not contact.osint_data.get("no_results"):
                # check if enriched recently (e.g. within 30 days)
                enriched_at_str = contact.osint_data.get("enriched_at")
                if enriched_at_str:
                    enriched_at = datetime.fromisoformat(enriched_at_str)
                    if datetime.now() - enriched_at < timedelta(days=OSINT_ENRICHMENT_DELAY_DAYS):
                        return {"status": "cached", "data": contact.osint_data}

        # 1. Search profiles
        candidates = await self.search_potential_profiles(contact_id)
        
        if not candidates:
            # Mark as no results
            result = await self.session.execute(
                select(Contact).where(Contact.id == contact_id)
            )
            contact = result.scalar_one_or_none()
            if contact:
                contact.osint_data = {"no_results": True, "enriched_at": datetime.now().isoformat()}
                await self.session.commit()
            return {"status": "no_results", "message": "No profiles found"}

        # 2. Pick best candidate (Auto-mode: Pick first)
        # TODO: Implement better selection logic (e.g. match title/company)
        best_candidate = candidates[0]
        
        # 3. Enrich
        return await self.enrich_contact_final(contact_id, best_candidate["url"])

    # Keep existing helper methods
    async def get_enrichment_stats(self, user_id: uuid.UUID) -> Dict[str, int]:
        """Get enrichment statistics for a user."""
        total_query = select(func.count(Contact.id)).where(Contact.user_id == user_id)
        total_result = await self.session.execute(total_query)
        total_contacts = total_result.scalar() or 0

        enriched_query = select(func.count(Contact.id)).where(
            Contact.user_id == user_id,
            Contact.osint_data.isnot(None),
            Contact.osint_data != {}
        )
        enriched_result = await self.session.execute(enriched_query)
        enriched_contacts = enriched_result.scalar() or 0

        return {
            "total_contacts": total_contacts,
            "enriched_contacts": enriched_contacts,
            "pending_enrichment": total_contacts - enriched_contacts
        }

    async def batch_enrich(self, user_id: uuid.UUID, limit: int = 5) -> Dict[str, Any]:
        """Batch enrich contacts."""
        query = select(Contact).where(
            Contact.user_id == user_id,
            Contact.name != UNKNOWN_CONTACT_NAME,
            (Contact.osint_data.is_(None) | (Contact.osint_data == {}))
        ).limit(limit)

        result = await self.session.execute(query)
        contacts = result.scalars().all()

        if not contacts:
            return {"status": "complete", "message": "All done", "enriched": 0}

        enriched = 0
        errors = []
        for contact in contacts:
            try:
                res = await self.enrich_contact(contact.id)
                if res["status"] == "success":
                    enriched += 1
                await asyncio.sleep(BATCH_ENRICHMENT_DELAY_SECONDS)  # Polite delay
            except Exception as e:
                errors.append(str(e))
        
        return {"status": "success", "enriched": enriched, "errors": errors}


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
