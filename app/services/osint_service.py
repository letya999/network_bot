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
from app.infrastructure.clients.tavily import TavilyClient
from app.config.constants import (
    UNKNOWN_CONTACT_NAME,
    OSINT_ENRICHMENT_DELAY_DAYS,
    BATCH_ENRICHMENT_DELAY_SECONDS
)

logger = logging.getLogger(__name__)


class OSINTService:
    """Service for enriching contacts with OSINT data."""

    def __init__(self, session: AsyncSession, tavily_api_key: str = None, gemini_api_key: str = None):
        self.session = session
        tavily_key = tavily_api_key or settings.TAVILY_API_KEY
        self.tavily_client = TavilyClient(tavily_key) if tavily_key else None
        self.gemini = GeminiService(api_key=gemini_api_key)

    async def _tavily_search(self, query: str, include_domains: List[str] = None) -> List[Dict[str, Any]]:
        """
        Perform a search using Tavily AI API.
        Returns rich results with content.
        """
        if not self.tavily_client:
            logger.warning("Tavily client not configured")
            return []

        return await self.tavily_client.search(query, include_domains=include_domains)

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


