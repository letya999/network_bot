from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from app.models.contact import Contact
from app.models.user import User
from app.services.gemini_service import GeminiService
from typing import List, Dict, Any, Optional
import uuid
import json
import logging

logger = logging.getLogger(__name__)

class MatchService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.gemini = GeminiService()

    def _format_contact_context(self, contact: Contact) -> str:
        """
        Create a rich text representation of the contact for AI matching,
        combining DB fields and OSINT enrichment.
        """
        # Basic info
        lines = [
            f"ID: {contact.id}",
            f"Name: {contact.name}",
            f"Company: {contact.company}",
            f"Role: {contact.role}",
        ]
        
        if contact.what_looking_for:
            lines.append(f"Looking for: {contact.what_looking_for}")
        if contact.can_help_with:
            lines.append(f"Can help with: {contact.can_help_with}")
            
        # OSINT Enrichment
        if contact.osint_data:
            osint = contact.osint_data
            
            # Add extended career info
            career = osint.get("career", {})
            current = career.get("current", {})
            if current and current.get("description"):
                lines.append(f"Role Description: {current['description']}")
            
            # Keywords/Skills from keywords field if we calculate them, or just raw interests
            personal = osint.get("personal", {})
            if personal.get("interests"):
                lines.append(f"Interests: {', '.join(personal['interests'])}")
            
            # Add recent publications titles as context for expertise
            pubs = osint.get("publications", [])
            if pubs:
                titles = [p['title'] for p in pubs[:3] if p.get('title')]
                lines.append(f"Content content/Publications: {'; '.join(titles)}")

        return "\n".join(lines)

    async def get_user_matches(self, contact: Contact, user: User) -> Dict[str, Any]:
        """
        Find matches between a new contact and the user's profile.
        Returns a dict with is_match, match_score, synergy_summary, suggested_pitch.
        """
        if not user.profile_data:
            return {"is_match": False, "match_score": 0, "synergy_summary": "Профиль пользователя не заполнен."}

        profile_a = json.dumps(user.profile_data, ensure_ascii=False)
        profile_b = self._format_contact_context(contact)
        
        prompt = self.gemini.get_prompt("find_matches")
        prompt = prompt.replace("{profile_a}", profile_a).replace("{profile_b}", profile_b)
        
        try:
            match_data = await self.gemini.extract_contact_data(prompt_template=prompt)
            return match_data
        except Exception as e:
            logger.error(f"Error finding matches: {e}")
            return {"is_match": False, "match_score": 0, "error": str(e)}

    async def find_peer_matches(self, contact: Contact, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Find matches between this contact and other contacts in the user's database.
        """
        # Get other active contacts
        stmt = select(Contact).where(
            Contact.user_id == contact.user_id,
            Contact.id != contact.id,
            Contact.status == "active"
        ).order_by(Contact.created_at.desc()).limit(limit)
        
        result = await self.session.execute(stmt)
        other_contacts = result.scalars().all()
        
        matches = []
        # Optimization: Only match against people who have some bio/needs or enrich data
        potential_peers = [c for c in other_contacts if c.what_looking_for or c.can_help_with or c.osint_data]
        
        contact_profile = self._format_contact_context(contact)

        # Limit to top 5 to avoid API hitting limits in one go
        for peer in potential_peers[:5]:
             peer_profile = self._format_contact_context(peer)
             
             prompt = self.gemini.get_prompt("find_matches")
             prompt = prompt.replace("{profile_a}", contact_profile).replace("{profile_b}", peer_profile)
             match_data = await self.gemini.extract_contact_data(prompt_template=prompt)
             
             if match_data.get("is_match") and match_data.get("match_score", 0) > 60:
                 match_data["peer_id"] = str(peer.id)
                 match_data["peer_name"] = peer.name
                 matches.append(match_data)
                 
        return matches

    async def semantic_search(self, user_id: uuid.UUID, query: str) -> List[Dict[str, Any]]:
        """
        Perform semantic search using Gemini.
        """
        # Get all contacts for the user to provide as context
        # In a real system with many contacts, we'd use vector embeddings.
        # Here, we'll try to provide a list of contacts to Gemini if there aren't too many.
        stmt = select(Contact).where(Contact.user_id == user_id)
        result = await self.session.execute(stmt)
        contacts = result.scalars().all()
        
        contact_list_str = ""
        for c in contacts:
            contact_list_str += self._format_contact_context(c) + "\n---\n"

        prompt = f"""
        Act as a professional networking assistant. 
        I have a list of contacts and I want to find someone based on a natural language query.
        
        Query: "{query}"
        
        Contacts:
        {contact_list_str}
        
        Task:
        Identify which contacts from the list best match the query. 
        Consider synonyms, roles, industries, and their needs/offers.
        
        Output a JSON object:
        {{
          "matches": [
            {{
              "contact_id": "UUID from the list",
              "reason": "Short explanation in Russian why this contact matches the query"
            }},
            ...
          ]
        }}
        
        If no matches found, return empty matches list.
        """
        
        try:
            search_results = await self.gemini.extract_contact_data(prompt_template=prompt)
            return search_results.get("matches", [])
        except Exception as e:
            logger.error(f"Semantic search error: {e}")
            return []
