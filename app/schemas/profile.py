from pydantic import BaseModel, Field
from typing import List, Optional

class SocialLink(BaseModel):
    platform: str
    url: str

class UserProfile(BaseModel):
    full_name: Optional[str] = None
    bio: Optional[str] = Field(None, description="Short bio or summary")
    company: Optional[str] = None
    job_title: Optional[str] = None
    location: Optional[str] = None
    interests: List[str] = Field(default_factory=list)
    social_links: List[SocialLink] = Field(default_factory=list)
    # Personal assets
    pitches: List[str] = Field(default_factory=list, description="List of elevator pitches")
    one_pagers: List[str] = Field(default_factory=list, description="List of links or text for one-pagers")
    welcome_messages: List[str] = Field(default_factory=list, description="List of welcome messages")
    
    # Contact info to share
    phone: Optional[str] = None
    email: Optional[str] = None
    telegram: Optional[str] = None
    website: Optional[str] = None
