from fastapi import APIRouter, Depends
from fastapi import HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from mcp_host.database.db import get_db
from mcp_host.models.users import User as UserModel
from mcp_host.services.auths import signup_user, login_user, get_current_user

auth_router = APIRouter()


class SignUpRequest(BaseModel):
    name: str
    email: str
    phone_number: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@auth_router.post("/signup")
async def signup(req: SignUpRequest, db: AsyncSession = Depends(get_db)):
    user = await signup_user(db, req.name, req.email, req.phone_number, req.password)
    return {"id": str(user.id), "email": user.email, "name": user.name}


@auth_router.post("/token", response_model=TokenResponse)
async def token(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    access_token = await login_user(db, req.email, req.password)
    return {"access_token": access_token, "token_type": "bearer"}


@auth_router.get("/me")
async def me(current_user=Depends(get_current_user)):
    return {
        "id": str(current_user.id),
        "email": current_user.email,
        "name": current_user.name,
    }
