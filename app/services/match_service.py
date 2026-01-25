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

    async def get_user_matches(self, contact: Contact, user: User) -> Dict[str, Any]:
        """
        Find matches between a new contact and the user's profile.
        Returns a dict with is_match, match_score, synergy_summary, suggested_pitch.
        """
        if not user.profile_data:
            return {"is_match": False, "match_score": 0, "synergy_summary": "Профиль пользователя не заполнен."}

        profile_a = json.dumps(user.profile_data, ensure_ascii=False)
        profile_b = f"Name: {contact.name}\nCompany: {contact.company}\nRole: {contact.role}\nLooking for: {contact.what_looking_for}\nCan help with: {contact.can_help_with}"
        
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
        # To avoid too many API calls, we might want to batch this or use a different approach.
        # For now, let's just do it for the most recent potential ones if they have 'looking_for' or 'can_help'
        potential_peers = [c for c in other_contacts if c.what_looking_for or c.can_help_with]
        
        # Limit to top 5 to avoid API hitting limits in one go
        for peer in potential_peers[:5]:
             profile_a = f"Name: {contact.name}\nLooking for: {contact.what_looking_for}\nCan help with: {contact.can_help_with}"
             profile_b = f"Name: {peer.name}\nLooking for: {peer.what_looking_for}\nCan help with: {peer.can_help_with}"
             
             prompt = self.gemini.get_prompt("find_matches")
             prompt = prompt.replace("{profile_a}", profile_a).replace("{profile_b}", profile_b)
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
        for i, c in enumerate(contacts):
            contact_list_str += f"{i}. ID: {c.id}, Name: {c.name}, Company: {c.company}, Role: {c.role}, Looking for: {c.what_looking_for}, Can help with: {c.can_help_with}, Events: {c.event_name}\n"

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
