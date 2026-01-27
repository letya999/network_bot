from sqlalchemy.ext.asyncio import AsyncSession
from app.services.user_service import UserService
from app.schemas.profile import UserProfile

class ProfileService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.user_service = UserService(session)

    async def get_profile(self, telegram_id: int) -> UserProfile:
        user = await self.user_service.get_or_create_user(telegram_id)
        data = user.profile_data or {}
        # Ensure 'full_name' defaults to user.name if not in profile_data
        if "full_name" not in data and user.name:
            data["full_name"] = user.name
            
        return UserProfile(**data)

    async def update_profile_field(self, telegram_id: int, field: str, value: any) -> UserProfile:
        """Update a single field in the profile"""
        user = await self.user_service.get_or_create_user(telegram_id)
        # Create a copy to ensure SQLAlchemy detects change
        current_data = dict(user.profile_data) if user.profile_data else {}
        
        current_data[field] = value
        
        if field == "full_name":
            user.name = value
            
        # Verify it validates and ensure serialization of nested models
        profile = UserProfile(**current_data)
        serialized_data = profile.model_dump(mode='json')
            
        user.profile_data = serialized_data
        
        await self.session.commit()
        await self.session.refresh(user)
        return profile

    async def update_full_profile(self, telegram_id: int, profile: UserProfile) -> UserProfile:
        user = await self.user_service.get_or_create_user(telegram_id)
        data = profile.model_dump(mode='json')
        user.profile_data = data
        if profile.full_name:
            user.name = profile.full_name
            
        await self.session.commit()
        await self.session.refresh(user)
        return profile
