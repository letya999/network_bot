
import aiohttp
import logging
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from app.core.config import settings
from app.models.contact import Contact

logger = logging.getLogger(__name__)

class NotionService:
    BASE_URL = "https://api.notion.com/v1"

    def __init__(self):
        self.api_key = settings.NOTION_API_KEY
        self.database_id = settings.NOTION_DATABASE_ID
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json"
        }

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
                    # Assuming "Name" is the title property. Adjust if needed.
                    # We look for the property that is of type 'title'
                    title_prop_name = None
                    for key, val in props.items():
                        if val.get("id") == "title": # This is internal ID, but type is safer
                            pass
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
        This assumes a specific schema in Notion.
        Users should create a DB with these columns or we fail gracefully if cols don't exist (Notion ignores unknown props usually? No, it errors if prop missing).
        
        To make it robust, we should only send properties that match the simple types.
        """
        # We assume the user has flexible setup. We'll map standard fields.
        # Note: In a real prod app, we might query the DB schema first to see what columns exist.
        # For this MVP, we enforce a schema or try to send common ones.
        
        props = {}

        # 1. Name (Title)
        props["Name"] = {
            "title": [{"text": {"content": contact.name or "Unknown"}}]
        }

        # 2. Company (Rich Text)
        if contact.company:
            props["Company"] = {
                "rich_text": [{"text": {"content": contact.company}}]
            }
        
        # 3. Role (Rich Text)
        if contact.role:
            props["Role"] = {
                "rich_text": [{"text": {"content": contact.role}}]
            }

        # 4. Email (Email)
        if contact.email:
            props["Email"] = {
                "email": contact.email
            }
            
        # 5. Phone (Phone)
        if contact.phone:
            props["Phone"] = {
                "phone_number": contact.phone
            }

        # 6. Telegram (Url or Text)
        if contact.telegram_username:
            # Clean username
            tg = contact.telegram_username
            url = f"https://t.me/{tg.replace('@', '')}"
            props["Telegram"] = {
                "url": url
            }

        # 7. Status (Select)
        if contact.status:
            props["Status"] = {
                "select": {"name": contact.status}
            }
            
        # 8. Topics (Multi-select)
        if contact.topics:
            # Limit to 100 chars per option as per Notion limits?
            # Also multi-select options must be created if not exist, Notion does this auto if configured?
            # Creating options via API inside property value works for Select/Multi-select in pages.
            options = [{"name": t[:100]} for t in contact.topics[:10]] # Limit to 10 topics
            props["Topics"] = {
                "multi_select": options
            }

        return props
