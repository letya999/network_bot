from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.user import User
import uuid

class UserService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_or_create_user(self, telegram_id: int, username: str = None, first_name: str = None) -> User:
        stmt = select(User).where(User.telegram_id == telegram_id)
        result = await self.session.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            user = User(
                telegram_id=telegram_id,
                name=first_name,
                profile_data={"username": username}
            )
            self.session.add(user)
            await self.session.commit()
            await self.session.refresh(user)
        else:
            # Update info if provided
            updated = False
            if first_name and user.name != first_name:
                user.name = first_name
                updated = True
            
            if username:
                current_data = dict(user.profile_data) if user.profile_data else {}
                if current_data.get("username") != username:
                    current_data["username"] = username
                    user.profile_data = current_data
                    updated = True
            
            if updated:
                await self.session.commit()
        
        return user

    async def get_user(self, telegram_id: int) -> User:
        stmt = select(User).where(User.telegram_id == telegram_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def update_custom_prompt(self, telegram_id: int, prompt_text: str):
        stmt = select(User).where(User.telegram_id == telegram_id)
        result = await self.session.execute(stmt)
        user = result.scalar_one_or_none()
        if user:
            user.custom_prompt = prompt_text
            await self.session.commit()
            await self.session.refresh(user)
        return user

    async def get_all_users(self):
        stmt = select(User)
        result = await self.session.execute(stmt)
        return result.scalars().all()
