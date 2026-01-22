import csv
import io
from typing import List
from app.models.contact import Contact

class ExportService:
    @staticmethod
    def to_csv(contacts: List[Contact]) -> io.BytesIO:
        output = io.StringIO()
        writer = csv.writer(output)
        
        headers = [
            "Name", "Company", "Role", "Phone", "Telegram", "Email", "LinkedIn", 
            "Event", "Date", "Looking For", "Can Help With", "Follow Up", "Notes"
        ]
        writer.writerow(headers)
        
        for c in contacts:
            writer.writerow([
                c.name,
                c.company,
                c.role,
                c.phone,
                c.telegram_username,
                c.email,
                c.linkedin_url,
                c.event_name,
                str(c.created_at.date()) if c.created_at else "",
                c.what_looking_for,
                c.can_help_with,
                c.follow_up_action,
                # We can include more fields or interactions
            ])
            
        output.seek(0)
        # Convert to bytes for Telegram
        return io.BytesIO(output.getvalue().encode('utf-8-sig')) # utf-8-sig for Excel compatibility
