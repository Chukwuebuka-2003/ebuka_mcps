import uuid
from typing import Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone
from fastapi import HTTPException
from mcp_host.models.users import User
from mcp_host.schemas.users import UserCreate, UserResponse, UserUpdate
import logging

logger = logging.getLogger(__name__)

class UsersService:

    @staticmethod
    async def list_users(db: AsyncSession):
        try:
            statement = select(User)
            result = await db.execute(statement)
            users = result.scalars().all()
            return [
                UserResponse.model_validate(user, from_attributes=True)
                for user in users
            ]
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @staticmethod
    async def create_user(user_create: UserCreate, db: AsyncSession):
        try:
            statement = select(User).where(User.email == user_create.email)
            result = await db.execute(statement)
            user = result.scalar_one_or_none()
            if user:
                raise HTTPException(status_code=400, detail="User already exists")

            user = User(
                **user_create.model_dump(),
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)
            return UserResponse.model_validate(user, from_attributes=True)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @staticmethod
    async def get_user_by_id(user_id: UUID, db: AsyncSession):
        try:
            statement = select(User).where(User.id == user_id)
            result = await db.execute(statement)
            user = result.scalar_one_or_none()
            if not user:
                raise HTTPException(status_code=404, detail="User not found")
            return UserResponse.model_validate(user, from_attributes=True)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @staticmethod
    async def update_user(user_id: UUID, user_update: UserUpdate, db: AsyncSession):
        try:
            statement = select(User).where(User.id == user_id)
            result = await db.execute(statement)
            user = result.scalar_one_or_none()
            if not user:
                raise HTTPException(status_code=404, detail="User not found")

            for key, value in user_update.model_dump(exclude_unset=True).items():
                if value is not None:
                    setattr(user, key, value)

            await db.commit()
            await db.refresh(user)
            return UserResponse.model_validate(user, from_attributes=True)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @staticmethod
    async def delete_user(user_id: UUID, db: AsyncSession):
        try:
            statement = select(User).where(User.id == user_id)
            result = await db.execute(statement)
            user = result.scalar_one_or_none()
            if not user:
                raise HTTPException(status_code=404, detail="User not found")
            await db.delete(user)
            await db.commit()
            return {"message": "User deleted successfully"}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
