from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from app.models.contact import Contact
from app.models.user import User
from app.services.gemini_service import GeminiService
from typing import List, Dict, Any, Optional
import uuid
import json
import logging
from app.config.constants import MAX_SEMANTIC_SEARCH_CONTACTS

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

        if contact.telegram_username:
            lines.append(f"Telegram: @{contact.telegram_username}")
        if contact.email:
             lines.append(f"Email: {contact.email}")
        if contact.phone:
            lines.append(f"Phone: {contact.phone}")
        if contact.linkedin_url:
            lines.append(f"LinkedIn: {contact.linkedin_url}")
        
        if contact.what_looking_for:
            lines.append(f"Looking for: {contact.what_looking_for}")
        if contact.can_help_with:
            lines.append(f"Can help with: {contact.can_help_with}")
            
        # OSINT Enrichment
        if contact.osint_data:
            osint = contact.osint_data
            
            # --- Career ---
            career = osint.get("career", {})
            current = career.get("current", {})
            if current and current.get("description"):
                lines.append(f"Role Description: {current['description']}")
            
            previous_positions = career.get("previous", [])
            if previous_positions:
                prev_list = []
                for position in previous_positions:
                    p_str = f"{position.get('role', 'Empl')} @ {position.get('company', 'Unknown')}"
                    if position.get("years"):
                        p_str += f" ({position['years']})"
                    prev_list.append(p_str)
                lines.append(f"Previous roles: {'; '.join(prev_list)}")

            # --- Education ---
            education = osint.get("education", {})
            universities = education.get("universities", [])
            if universities:
                uni_list = []
                for university in universities:
                    u_str = university.get("name", "")
                    if university.get("degree"):
                        u_str += f" ({university['degree']})"
                    uni_list.append(u_str)
                lines.append(f"Education: {'; '.join(uni_list)}")
            
            courses = education.get("courses", [])
            if courses:
                course_list = [course.get("name", "") for course in courses if course.get("name")]
                lines.append(f"Courses: {'; '.join(course_list)}")

            # --- Geography ---
            geography = osint.get("geography", {})
            if geography.get("birthplace"):
                lines.append(f"Birthplace: {geography['birthplace']}")
            if geography.get("current_city"):
                lines.append(f"Current City: {geography['current_city']}")
            if geography.get("lived_in"):
                lines.append(f"Lived in: {', '.join(geography['lived_in'])}")

            # --- Personal ---
            personal = osint.get("personal", {})
            if personal.get("interests"):
                lines.append(f"Interests: {', '.join(personal['interests'])}")
            
            # --- Publications ---
            publications = osint.get("publications", [])
            if publications:
                titles = [pub['title'] for pub in publications[:5] if pub.get('title')]
                lines.append(f"Publications: {'; '.join(titles)}")

        return "\n".join(lines)

    async def get_user_matches(self, contact: Contact, user: User) -> Dict[str, Any]:
        """
        Find matches between a new contact and the user's profile.
        Returns a dict with is_match, match_score, synergy_summary, suggested_pitch.
        """
        if not user.profile_data and not user.name:
            return {"is_match": False, "match_score": 0, "synergy_summary": "Профиль пользователя не заполнен."}

        # Prepare user profile data with name
        user_data = dict(user.profile_data) if user.profile_data else {}
        if user.name and "name" not in user_data:
            user_data["name"] = user.name
            
        profile_a = json.dumps(user_data, ensure_ascii=False)
        profile_b = self._format_contact_context(contact)
        
        prompt = self.gemini.get_prompt("find_matches")
        prompt = prompt.replace("{profile_a}", profile_a).replace("{profile_b}", profile_b)
        
        try:
            match_data = await self.gemini.extract_contact_data(prompt_template=prompt)
            return match_data
        except Exception as e:
            logger.exception("Error finding matches")
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
        # Provide recent contacts as context. Vector search (pgvector) is recommended for larger sets.
        stmt = (
            select(Contact)
            .where(Contact.user_id == user_id)
            .order_by(Contact.updated_at.desc().nulls_last(), Contact.created_at.desc())
            .limit(MAX_SEMANTIC_SEARCH_CONTACTS)
        )
        result = await self.session.execute(stmt)
        contacts = result.scalars().all()
        
        contact_list_str = ""
        for contact in contacts:
            contact_list_str += self._format_contact_context(contact) + "\n---\n"

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
        except Exception:
            logger.exception("Semantic search error")
            return []
