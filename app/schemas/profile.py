from pydantic import BaseModel, Field, model_validator
from typing import List, Optional, Any
import uuid
import hashlib

class SocialLink(BaseModel):
    platform: str
    url: str


class CustomContact(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    label: str
    value: str

class ContentItem(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str
    content: str
    type: str = "text"

class UserProfile(BaseModel):
    full_name: Optional[str] = None
    bio: Optional[str] = Field(None, description="Short bio or summary")
    company: Optional[str] = None
    job_title: Optional[str] = None
    location: Optional[str] = None
    interests: List[str] = Field(default_factory=list)
    social_links: List[SocialLink] = Field(default_factory=list)
    custom_contacts: List[CustomContact] = Field(default_factory=list)
    
    # Personal assets
    pitches: List[ContentItem] = Field(default_factory=list, description="List of elevator pitches")
    one_pagers: List[ContentItem] = Field(default_factory=list, description="List of one-pagers")
    welcome_messages: List[ContentItem] = Field(default_factory=list, description="List of welcome messages")
    
    # Contact info to share
    phone: Optional[str] = None
    email: Optional[str] = None
    telegram: Optional[str] = None
    website: Optional[str] = None

    @model_validator(mode='before')
    @classmethod
    def migrate_strings(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # Ensure lists
            if 'custom_contacts' not in data: data['custom_contacts'] = []
            
            for field_name in ['pitches', 'one_pagers', 'welcome_messages']:
                if field_name in data:
                    raw_list = data[field_name]
                    new_list = []
                    if raw_list and isinstance(raw_list, list):
                        for i, item in enumerate(raw_list):
                            if isinstance(item, str):
                                # Convert string to ContentItem
                                prefix = "Pitch"
                                if field_name == 'one_pagers': prefix = "One-Pager"
                                elif field_name == 'welcome_messages': prefix = "Greeting"
                                
                                new_list.append({
                                    "id": hashlib.md5(item.encode("utf-8")).hexdigest()[:8],
                                    "name": f"{prefix} {i+1}",
                                    "content": item,
                                    "type": "text"
                                })
                            else:
                                new_list.append(item)
                    data[field_name] = new_list
        return data
