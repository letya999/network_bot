"""CSV import service for LinkedIn and other contact sources."""
import csv
import io
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.contact_service import ContactService

logger = logging.getLogger(__name__)


class CSVImportService:
    """Service for importing contacts from CSV files."""

    def __init__(self, session: AsyncSession):
        """
        Initialize CSV import service.

        Args:
            session: Database session
        """
        self.session = session
        self.contact_service = ContactService(session)

    async def import_linkedin_csv(
        self,
        user_id: str,
        csv_content: str
    ) -> Tuple[int, int, List[str]]:
        """
        Import contacts from LinkedIn CSV export.

        Args:
            user_id: ID of the user importing contacts
            csv_content: CSV file content as string

        Returns:
            Tuple of (imported_count, skipped_count, errors_list)
        """
        reader = csv.DictReader(io.StringIO(csv_content))

        imported = 0
        skipped = 0
        errors = []

        for row in reader:
            try:
                # LinkedIn export format varies, try common field names
                first_name = row.get("First Name", row.get("first_name", ""))
                last_name = row.get("Last Name", row.get("last_name", ""))
                name = f"{first_name} {last_name}".strip()

                if not name:
                    skipped += 1
                    continue

                company = row.get("Company", row.get("company", ""))
                position = row.get("Position", row.get("position", row.get("Title", "")))
                email = row.get("Email Address", row.get("email", ""))
                linkedin_url = row.get("URL", row.get("Profile URL", row.get("linkedin_url", "")))

                # Check for duplicates
                existing = await self.contact_service.find_contacts(user_id, name)
                if existing:
                    # Check if it's the same person (same company)
                    for ex in existing:
                        if ex.company and company and ex.company.lower() == company.lower():
                            skipped += 1
                            break
                    else:
                        # Different company, might be different person - import anyway
                        pass

                # Create contact data
                contact_data = {
                    "name": name,
                    "company": company if company else None,
                    "role": position if position else None,
                    "email": email if email else None,
                    "linkedin_url": linkedin_url if linkedin_url else None,
                    "notes": "Imported from LinkedIn CSV",
                }

                # Connected On date if available
                connected_on = row.get("Connected On", "")
                if connected_on:
                    try:
                        event_date = datetime.strptime(connected_on, "%d %b %Y")
                        contact_data["event_date"] = event_date.date()
                        contact_data["event"] = "LinkedIn Connection"
                    except ValueError:
                        pass

                await self.contact_service.create_contact(user_id, contact_data)
                imported += 1

            except Exception as e:
                logger.error(f"Error importing row: {e}")
                errors.append(str(e))

        return imported, skipped, errors

    def parse_generic_csv(self, csv_content: str) -> List[Dict[str, str]]:
        """
        Parse a generic CSV file into list of dictionaries.

        Args:
            csv_content: CSV file content as string

        Returns:
            List of row dictionaries
        """
        try:
            reader = csv.DictReader(io.StringIO(csv_content))
            return list(reader)
        except Exception as e:
            logger.error(f"Error parsing CSV: {e}")
            return []

    @staticmethod
    def validate_csv_file(
        file_name: str,
        file_size: int,
        max_size_mb: int = 5
    ) -> Optional[str]:
        """
        Validate CSV file parameters.

        Args:
            file_name: Name of the file
            file_size: Size of the file in bytes
            max_size_mb: Maximum allowed size in MB

        Returns:
            Error message if validation fails, None if valid
        """
        if not file_name.endswith(".csv"):
            return "Пожалуйста, отправь файл в формате CSV."

        max_size_bytes = max_size_mb * 1024 * 1024
        if file_size > max_size_bytes:
            return f"Файл слишком большой. Максимум {max_size_mb} МБ."

        return None
