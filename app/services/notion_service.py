
import aiohttp
import logging
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from app.core.config import settings
from app.models.contact import Contact

logger = logging.getLogger(__name__)

class NotionService:
    BASE_URL = "https://api.notion.com/v1"

    def __init__(self, api_key: str = None, database_id: str = None):
        self.api_key = api_key or settings.NOTION_API_KEY
        self.database_id = database_id or settings.NOTION_DATABASE_ID
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json"
        }
        self.schema_map = {} # Canonical (lowercase) -> Actual Notion Property Name
        self.schema_types = {} # Property Name -> Property Type

    async def _ensure_schema(self, session: aiohttp.ClientSession):
        """
        Fetch database schema to map properties case-insensitively and avoid sending missing fields.
        """
        if self.schema_map:
            return

        url = f"{self.BASE_URL}/databases/{self.database_id}"
        async with session.get(url, headers=self.headers) as resp:
            if resp.status != 200:
                text = await resp.text()
                logger.error(f"Failed to fetch Notion DB schema ({resp.status}): {text}")
                return
            
            data = await resp.json()
            properties = data.get("properties", {})
            
            for prop_name, prop_data in properties.items():
                self.schema_map[prop_name.lower()] = prop_name
                self.schema_types[prop_name] = prop_data.get("type")
                
            logger.info(f"Loaded Notion schema: {list(self.schema_map.keys())}")

    async def sync_contacts(self, contacts: List[Contact]) -> Dict[str, int]:
        """
        Syncs a list of contacts to Notion.
        Returns statistics: {"created": 0, "updated": 0, "failed": 0, "skipped": 0}
        """
        if not self.api_key or not self.database_id:
            logger.warning("Notion credentials not set. Skipping sync.")
            return {"error": "Notion details not configured"}

        stats = {"created": 0, "updated": 0, "failed": 0, "skipped": 0}

        async with aiohttp.ClientSession() as session:
            # 0. Load Schema
            await self._ensure_schema(session)
            
            # 1. Get existing pages to avoid duplicates (naive check by Name)
            existing_pages = await self._get_existing_pages(session)
            
            for contact in contacts:
                try:
                    # Check if contact already exists in Notion (by name)
                    # Ideally we should use a unique ID, but Name is a start for a simple sync.
                    page_id = existing_pages.get(contact.name)

                    if page_id:
                        # Update
                        await self._update_page(session, page_id, contact)
                        stats["updated"] += 1
                    else:
                        # Create
                        await self._create_page(session, contact)
                        stats["created"] += 1
                        
                except Exception as e:
                    logger.error(f"Failed to sync contact {contact.name}: {e}")
                    stats["failed"] += 1

        return stats

    async def _get_existing_pages(self, session: aiohttp.ClientSession) -> Dict[str, str]:
        """
        Fetches all pages from the database to build a map of Name -> PageID.
        """
        url = f"{self.BASE_URL}/databases/{self.database_id}/query"
        name_map = {}
        has_more = True
        next_cursor = None

        while has_more:
            payload = {"page_size": 100}
            if next_cursor:
                payload["start_cursor"] = next_cursor

            async with session.post(url, headers=self.headers, json=payload) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    logger.error(f"Error querying Notion DB ({resp.status}): {text}")
                    break
                
                data = await resp.json()
                results = data.get("results", [])
                
                for page in results:
                    props = page.get("properties", {})
                    # Find title property dynamically using schema or searching
                    title_prop_name = None
                    
                    # Try to find 'title' type property
                    for key, val in props.items():
                        if val.get("type") == "title":
                            title_prop_name = key
                            break
                    
                    if title_prop_name:
                        title_list = props[title_prop_name].get("title", [])
                        if title_list:
                            name = "".join([t.get("plain_text", "") for t in title_list])
                            name_map[name] = page["id"]

                has_more = data.get("has_more", False)
                next_cursor = data.get("next_cursor")

        return name_map

    async def _create_page(self, session: aiohttp.ClientSession, contact: Contact):
        url = f"{self.BASE_URL}/pages"
        properties = self._map_contact_to_properties(contact)
        payload = {
            "parent": {"database_id": self.database_id},
            "properties": properties
        }
        
        async with session.post(url, headers=self.headers, json=payload) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise Exception(f"Failed to create page: {text}")

    async def _update_page(self, session: aiohttp.ClientSession, page_id: str, contact: Contact):
        url = f"{self.BASE_URL}/pages/{page_id}"
        properties = self._map_contact_to_properties(contact)
        if not properties:
            return 

        payload = {
            "properties": properties
        }
        
        async with session.patch(url, headers=self.headers, json=payload) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise Exception(f"Failed to update page: {text}")

    def _map_contact_to_properties(self, contact: Contact) -> Dict[str, Any]:
        """
        Maps Contact model fields to Notion Database properties.
        Only includes properties that exist in the target database.
        Automatically adapts value format to the target property type.
        """
        props = {}

        def add_prop(canonical: str, value: Any):
            actual_name = self.schema_map.get(canonical.lower())
            if not actual_name:
                return # Skip if property doesn't exist in Notion DB
            
            # Determine type from schema matches
            prop_type = self.schema_types.get(actual_name)
            if not prop_type:
                return 

            # Construct payload based on ACTUAL Notion type, not our assumption
            if prop_type == "title":
                props[actual_name] = {"title": [{"text": {"content": str(value)}}]}
                
            elif prop_type == "rich_text":
                # Convert anything to string for rich_text
                text_val = str(value)
                if isinstance(value, list):
                    text_val = ", ".join([str(v) for v in value])
                props[actual_name] = {"rich_text": [{"text": {"content": text_val}}]}
                
            elif prop_type == "email":
                props[actual_name] = {"email": str(value)}
                
            elif prop_type == "phone_number":
                props[actual_name] = {"phone_number": str(value)}
                
            elif prop_type == "url":
                props[actual_name] = {"url": str(value)}
                
            elif prop_type == "select":
                # Expects: {"name": "OptionName"}
                val_str = str(value)
                # Notion select options can't be empty or too long
                if val_str:
                    props[actual_name] = {"select": {"name": val_str[:100]}}
                    
            elif prop_type == "multi_select":
                # Expects: [{"name": "Option1"}, {"name": "Option2"}]
                if isinstance(value, list):
                    # Already a list (of dicts or strings?)
                    # If it's a list of dicts from our logic below
                    formatted = []
                    for item in value:
                        if isinstance(item, dict) and "name" in item:
                            formatted.append(item)
                        elif isinstance(item, str):
                            formatted.append({"name": item[:100].replace(",", "")})
                    props[actual_name] = {"multi_select": formatted}
                else:
                    # Single value but target is multi_select
                    if value:
                        props[actual_name] = {"multi_select": [{"name": str(value)[:100]}]}
                        
            elif prop_type == "date":
                props[actual_name] = {"date": {"start": str(value)}}

        # 1. Name (Title)
        add_prop("name", contact.name or "Unknown")

        # 2. Company
        if contact.company:
            add_prop("company", contact.company)
        
        # 3. Role
        if contact.role:
            add_prop("role", contact.role)

        # 4. Email
        if contact.email:
            add_prop("email", contact.email)
            
        # 5. Phone
        if contact.phone:
            add_prop("phone", contact.phone)

        # 6. Telegram
        if contact.telegram_username:
            tg = contact.telegram_username
            url = f"https://t.me/{tg.replace('@', '')}"
            
            # Check aliases
            for alias in ["telegram", "telegram_username", "tg", "t.me"]:
                if self.schema_map.get(alias):
                    add_prop(alias, url)
                    break

        # 7. Status
        if contact.status:
            # We pass the raw string, `add_prop` handles if it needs select or multi_select wrapper
            add_prop("status", contact.status)
            
        # 8. Topics
        if contact.topics:
            # We pass raw list of strings
            add_prop("topics", contact.topics)
            
        # 9. Event
        if contact.event_name:
            add_prop("event", contact.event_name)
            
        # 10. Data (Date)
        if contact.event_date:
            add_prop("date", contact.event_date)
            # Support alias 'Event Date' or 'Date'
            add_prop("event date", contact.event_date)

        return props
