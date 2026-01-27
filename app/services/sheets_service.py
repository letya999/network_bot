
import logging
import asyncio
from typing import List, Dict, Any, Optional
from app.core.config import settings
from app.models.contact import Contact

logger = logging.getLogger(__name__)

# Optional imports
try:
    import gspread
    from google.oauth2.service_account import Credentials
    HAS_GSPREAD = True
except ImportError:
    HAS_GSPREAD = False

class SheetsService:
    SCOPES = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]

    def __init__(self):
        self.sheet_id = settings.GOOGLE_SHEET_ID
        if self.sheet_id:
            # Clean sheet ID if user pasted full URL or path
            # Remove "https://docs.google.com/spreadsheets/d/" if present
            if "/d/" in self.sheet_id:
                self.sheet_id = self.sheet_id.split("/d/")[1].split("/")[0]
            elif self.sheet_id.startswith("d/"): # Handle cases like 'd/ID'
                 self.sheet_id = self.sheet_id[2:].split("/")[0]
        self.client = None
        
        if HAS_GSPREAD and self._has_credentials():
            try:
                creds_dict = self._get_creds_dict()
                creds = Credentials.from_service_account_info(creds_dict, scopes=self.SCOPES)
                self.client = gspread.authorize(creds)
            except Exception:
                logger.exception("Failed to initialize Sheets client")

    def _has_credentials(self):
        # Minimal check
        return bool(settings.GOOGLE_PRIVATE_KEY and settings.GOOGLE_CLIENT_EMAIL)

    def _get_creds_dict(self):
        # Reconstruct JSON from env vars
        pk = settings.GOOGLE_PRIVATE_KEY
        if pk and "\\n" in pk:
            pk = pk.replace("\\n", "\n")
            
        return {
            "type": "service_account",
            "project_id": settings.GOOGLE_PROJ_ID,
            "private_key_id": settings.GOOGLE_PRIVATE_KEY_ID,
            "private_key": pk,
            "client_email": settings.GOOGLE_CLIENT_EMAIL,
            "client_id": "TODO", 
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_x509_cert_url": f"https://www.googleapis.com/robot/v1/metadata/x509/{settings.GOOGLE_CLIENT_EMAIL}"
        }

    async def sync_contacts(self, contacts: List[Contact]) -> Dict[str, int]:
        """
        Syncs contacts to Google Sheets.
        Strategies:
        1. Read all existing rows.
        2. Match by Name.
        3. Update existing, append new.
        """
        if not HAS_GSPREAD:
            return {"error": "Missing dependencies: gspread, google-auth"}
        
        if not self.client or not self.sheet_id:
            return {"error": "Google Sheets keys not configured"}

        # Run blocking code in executor
        return await asyncio.to_thread(self._sync_sync, contacts)

    def _sync_sync(self, contacts: List[Contact]) -> Dict[str, int]:
        stats = {"created": 0, "updated": 0, "failed": 0, "skipped": 0}
        
        try:
            spreadsheet = self.client.open_by_key(self.sheet_id)
            try:
                worksheet = spreadsheet.worksheet("Contacts")
            except Exception:
                worksheet = spreadsheet.sheet1
                try:
                    worksheet.update_title("Contacts")
                except Exception:
                    pass

            # Headers
            headers = ["Name", "Company", "Role", "Phone", "Email", "Telegram", "Status", "Event", "Looking For", "Can Help", "Topics", "Notes", "Last Updated"]
            
            # Check/Write headers
            current_values = worksheet.get_all_values()
            
            # If empty or first row doesn't match headers, force write headers
            # Using safe check: if sheet is empty OR first cell is empty OR first row doesn't look like our header
            force_headers = False
            if not current_values:
                force_headers = True
            elif not current_values[0] or current_values[0][0] != headers[0]:
                force_headers = True
            
            if force_headers:
                # We update the first row explicitly
                print(f"Writing headers to {worksheet.title}")
                worksheet.update('A1:M1', [headers])
                # Reload or manually patch current_values
                if not current_values:
                    current_values = [headers]
                else:
                    current_values[0] = headers

            # Map Name -> Row Index (0-based list index)
            name_map = {}
            # We track the last used row to know where to append
            last_row_index = len(current_values) - 1 

            for index, row in enumerate(current_values):
                if index == 0: continue # Skip header
                if row:
                    name_map[row[0]] = index # Name is column 0

            # Collect batch updates for existing contacts
            batch_updates = []
            
            # For new rows, we can also use batch_update if we calculate the range
            # But appending one by one might be safer if concurrency is an issue (it's not here)
            # Efficient way: collect new rows and append them all at once at the end?
            # Or use batch_update for them too.
            
            new_rows_data = []

            for contact in contacts:
                try:
                    row_data = [
                        contact.name or "",
                        contact.company or "",
                        contact.role or "",
                        contact.phone or "",
                        contact.email or "",
                        f"https://t.me/{contact.telegram_username}" if contact.telegram_username else "",
                        contact.status or "",
                        contact.event_name or "",
                        contact.what_looking_for or "",
                        contact.can_help_with or "",
                        ", ".join(contact.topics) if contact.topics else "",
                        contact.attributes.get("notes") if contact.attributes else "",
                        contact.updated_at.strftime("%Y-%m-%d %H:%M") if contact.updated_at else ""
                    ]
                    
                    if contact.name in name_map:
                        # Prepare update for existing contact
                        row_index = name_map[contact.name]
                        # Row number in sheet is row_index + 1 (1-indexed)
                        batch_updates.append({
                            'range': f'A{row_index+1}:M{row_index+1}',
                            'values': [row_data]
                        })
                        stats["updated"] += 1
                    else:
                        # Append new contact to list
                        new_rows_data.append(row_data)
                        stats["created"] += 1
                        
                except Exception:
                    logger.exception(f"Error processing contact {contact.name}")
                    stats["failed"] += 1
            
            # Execute batch updates for existing rows
            if batch_updates:
                try:
                    worksheet.batch_update(batch_updates)
                    logger.info(f"Batch updated {len(batch_updates)} contacts in Google Sheets")
                except Exception:
                    logger.exception("Batch update failed")
                    stats["failed"] += len(batch_updates)
                    stats["updated"] -= len(batch_updates)

            # Append new rows in one go
            if new_rows_data:
                try:
                    # Append starting from last_row_index + 2 (1-based, +1 for next)
                    # Actually gspread append_rows is better for this
                    worksheet.append_rows(new_rows_data)
                    logger.info(f"Appended {len(new_rows_data)} new contacts")
                except Exception:
                    logger.exception("Append rows failed")
                    stats["failed"] += len(new_rows_data)
                    stats["created"] -= len(new_rows_data)
                    
        except gspread.exceptions.SpreadsheetNotFound:
            logger.error(f"Spreadsheet {self.sheet_id} not found. Please share the sheet with the service account email.")
            return {"error": "Таблица не найдена или нет доступа. Добавьте email бота в настройки доступа таблицы."}
        except Exception as e:
            logger.exception("Global Sheet Sync Error")
            return {"error": str(e)}
            
        return stats
