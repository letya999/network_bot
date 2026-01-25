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

logger = logging.getLogger(__name__)


class OSINTService:
    """Service for enriching contacts with OSINT data."""

    GOOGLE_CSE_URL = "https://www.googleapis.com/customsearch/v1"

    def __init__(self, session: AsyncSession):
        self.session = session
        self.gemini = GeminiService()

    def _is_configured(self) -> bool:
        """Check if OSINT service is properly configured."""
        return bool(settings.GOOGLE_CSE_API_KEY and settings.GOOGLE_CSE_CX)

    async def _google_search(self, query: str, num_results: int = 5) -> List[Dict[str, Any]]:
        """
        Perform a Google Custom Search.

        Args:
            query: Search query string
            num_results: Number of results to return (max 10)

        Returns:
            List of search results with title, link, and snippet
        """
        if not self._is_configured():
            logger.warning("Google CSE not configured - skipping search")
            return []

        params = {
            "key": settings.GOOGLE_CSE_API_KEY,
            "cx": settings.GOOGLE_CSE_CX,
            "q": query,
            "num": min(num_results, 10),
        }

        try:
            async with aiohttp.ClientSession() as http_session:
                async with http_session.get(
                    self.GOOGLE_CSE_URL, params=params, timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 429:
                        logger.warning("Google CSE rate limit exceeded")
                        return []
                    if response.status != 200:
                        logger.error(f"Google CSE error: {response.status}")
                        return []

                    data = await response.json()
                    items = data.get("items", [])

                    results = []
                    for item in items:
                        results.append({
                            "title": item.get("title", ""),
                            "link": item.get("link", ""),
                            "snippet": item.get("snippet", ""),
                        })
                    return results

        except asyncio.TimeoutError:
            logger.error("Google CSE request timed out")
            return []
        except Exception as e:
            logger.exception(f"Google CSE error: {e}")
            return []

    async def _search_linkedin(self, name: str, company: str = None) -> List[Dict[str, Any]]:
        """Search for LinkedIn profile information."""
        query_parts = [name]
        if company:
            query_parts.append(company)
        query_parts.append("site:linkedin.com/in")

        query = " ".join(query_parts)
        return await self._google_search(query, num_results=3)

    async def _search_publications(self, name: str, company: str = None) -> List[Dict[str, Any]]:
        """Search for publications, talks, and articles."""
        query_parts = [name]
        if company:
            query_parts.append(company)
        # Search for various content types
        query_parts.append("(article OR talk OR interview OR podcast OR presentation)")

        query = " ".join(query_parts)
        return await self._google_search(query, num_results=5)

    async def _search_social(self, name: str) -> List[Dict[str, Any]]:
        """Search for social media profiles."""
        query = f"{name} (site:twitter.com OR site:x.com OR site:facebook.com OR site:github.com)"
        return await self._google_search(query, num_results=5)

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

        input_data = {
            "contact": contact_info,
            "linkedin_results": raw_data.get("linkedin", []),
            "publication_results": raw_data.get("publications", []),
            "social_results": raw_data.get("social", []),
        }

        try:
            response = await self.gemini.model.generate_content_async(
                f"{prompt}\n\nInput Data:\n{json.dumps(input_data, ensure_ascii=False)}",
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
            logger.exception(f"Error structuring OSINT data: {e}")
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

    async def enrich_contact(
        self,
        contact_id: uuid.UUID,
        force: bool = False
    ) -> Dict[str, Any]:
        """
        Enrich a contact with OSINT data.

        Args:
            contact_id: UUID of the contact to enrich
            force: If True, re-enrich even if recently enriched

        Returns:
            Dictionary with enrichment status and data
        """
        # Get contact
        result = await self.session.execute(
            select(Contact).where(Contact.id == contact_id)
        )
        contact = result.scalar_one_or_none()

        if not contact:
            return {"status": "error", "message": "Contact not found"}

        # Check if already enriched recently
        if not force and contact.osint_data:
            enriched_at = contact.osint_data.get("enriched_at")
            if enriched_at:
                try:
                    enriched_date = datetime.fromisoformat(enriched_at)
                    if datetime.now() - enriched_date < timedelta(days=settings.OSINT_CACHE_DAYS):
                        return {
                            "status": "cached",
                            "message": f"Already enriched on {enriched_date.strftime('%Y-%m-%d')}",
                            "data": contact.osint_data
                        }
                except ValueError:
                    pass

        # Check if we have enough information to search
        if not contact.name or contact.name == "Неизвестно":
            return {"status": "error", "message": "Contact name is required for enrichment"}

        # Perform searches
        logger.info(f"Enriching contact {contact_id}: {contact.name}")

        raw_data = {}

        # LinkedIn search
        linkedin_results = await self._search_linkedin(contact.name, contact.company)
        raw_data["linkedin"] = linkedin_results

        # Add small delay to avoid rate limiting
        await asyncio.sleep(0.5)

        # Publications search
        publication_results = await self._search_publications(contact.name, contact.company)
        raw_data["publications"] = publication_results

        await asyncio.sleep(0.5)

        # Social media search
        social_results = await self._search_social(contact.name)
        raw_data["social"] = social_results

        # Check if we found anything
        total_results = (
            len(linkedin_results) + len(publication_results) + len(social_results)
        )
        if total_results == 0:
            return {
                "status": "no_results",
                "message": "No public information found",
                "data": {"enriched_at": datetime.now().isoformat(), "no_results": True}
            }

        # Structure the data using Gemini
        contact_info = {
            "name": contact.name,
            "company": contact.company,
            "role": contact.role,
        }

        structured_data = await self._structure_osint_data(raw_data, contact_info)

        # Update contact with OSINT data
        contact.osint_data = structured_data
        await self.session.commit()
        await self.session.refresh(contact)

        logger.info(f"Contact {contact_id} enriched successfully")

        return {
            "status": "success",
            "message": "Contact enriched successfully",
            "data": structured_data
        }

    async def get_enrichment_stats(self, user_id: uuid.UUID) -> Dict[str, int]:
        """Get enrichment statistics for a user."""
        # Count total contacts
        total_query = select(func.count(Contact.id)).where(Contact.user_id == user_id)
        total_result = await self.session.execute(total_query)
        total_contacts = total_result.scalar() or 0

        # Count enriched contacts
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

    async def batch_enrich(
        self,
        user_id: uuid.UUID,
        limit: int = 5
    ) -> Dict[str, Any]:
        """
        Batch enrich contacts that haven't been enriched yet.

        Args:
            user_id: User ID to enrich contacts for
            limit: Maximum number of contacts to enrich in this batch

        Returns:
            Dictionary with batch enrichment results
        """
        # Find contacts without OSINT data
        query = select(Contact).where(
            Contact.user_id == user_id,
            Contact.name != "Неизвестно",
            (Contact.osint_data.is_(None) | (Contact.osint_data == {}))
        ).limit(limit)

        result = await self.session.execute(query)
        contacts = result.scalars().all()

        if not contacts:
            return {"status": "complete", "message": "All contacts are enriched", "enriched": 0}

        enriched_count = 0
        errors = []

        for contact in contacts:
            try:
                result = await self.enrich_contact(contact.id)
                if result["status"] == "success":
                    enriched_count += 1
                else:
                    errors.append(f"{contact.name}: {result.get('message', 'Unknown error')}")

                # Rate limiting between enrichments
                await asyncio.sleep(1)

            except Exception as e:
                logger.exception(f"Error enriching contact {contact.id}: {e}")
                errors.append(f"{contact.name}: {str(e)}")

        return {
            "status": "partial" if errors else "success",
            "message": f"Enriched {enriched_count} contacts",
            "enriched": enriched_count,
            "errors": errors if errors else None
        }


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
        if current.get("company") and current.get("role"):
            career_str += f"   {current['role']} @ {current['company']}"
        elif current.get("company"):
            career_str += f"   {current['company']}"
        elif current.get("role"):
            career_str += f"   {current['role']}"

        if current.get("since"):
            career_str += f" (с {current['since']})"
        lines.append(career_str)

    previous = career.get("previous", [])
    if previous:
        for job in previous[:2]:  # Show max 2 previous jobs
            if job.get("company"):
                job_str = f"   ↳ {job.get('role', '')} @ {job['company']}"
                if job.get("years"):
                    job_str += f" ({job['years']})"
                lines.append(job_str)

    # Education
    education = osint_data.get("education", {})
    universities = education.get("universities", [])
    if universities:
        edu_str = "🎓 *Образование:*\n"
        for uni in universities[:2]:
            if uni.get("name"):
                edu_line = f"   {uni['name']}"
                if uni.get("degree"):
                    edu_line += f" — {uni['degree']}"
                if uni.get("year"):
                    edu_line += f" ({uni['year']})"
                edu_str += edu_line + "\n"
        lines.append(edu_str.rstrip())

    # Geography
    geography = osint_data.get("geography", {})
    if geography.get("current_city"):
        lines.append(f"📍 *Локация:* {geography['current_city']}")

    # Social links
    social = osint_data.get("social", {})
    social_links = []
    if social.get("linkedin"):
        social_links.append(f"[LinkedIn]({social['linkedin']})")
    if social.get("twitter"):
        twitter_url = social["twitter"]
        if not twitter_url.startswith("http"):
            twitter_url = f"https://twitter.com/{twitter_url.lstrip('@')}"
        social_links.append(f"[Twitter]({twitter_url})")
    if social.get("github"):
        github_url = social["github"]
        if not github_url.startswith("http"):
            github_url = f"https://github.com/{github_url}"
        social_links.append(f"[GitHub]({github_url})")

    if social_links:
        lines.append(f"🔗 *Соцсети:* {' • '.join(social_links)}")

    # Publications
    publications = osint_data.get("publications", [])
    if publications:
        pub_str = "📚 *Публикации:*\n"
        for pub in publications[:3]:  # Show max 3 publications
            if pub.get("title"):
                pub_type = pub.get("type", "article")
                type_emoji = {"article": "📄", "talk": "🎤", "podcast": "🎙️", "interview": "💬"}.get(pub_type, "📄")
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
