from fastapi import APIRouter, Depends, Form, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from mcp_host.database.db import get_db
from mcp_host.models.users import User as UserModel
from mcp_host.services.auths import signup_user, login_user, get_current_user
from mcp_host.schemas.auth import SignUpRequest, TokenResponse  # Import new schemas
# Removed LoginRequest import as it will be handled by Form()

auth_router = APIRouter()


@auth_router.post("/signup", response_model=TokenResponse)  # Changed response_model
async def signup(req: SignUpRequest, db: AsyncSession = Depends(get_db)):
    user = await signup_user(db, req.name, req.email, req.phone_number, req.password)
    # Automatically log in the user after successful signup
    access_token = await login_user(db, req.email, req.password)
    return {"access_token": access_token, "token_type": "bearer"}


@auth_router.post("/token", response_model=TokenResponse)
async def token(
    email: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    access_token = await login_user(db, email, password)
    return {"access_token": access_token, "token_type": "bearer"}


@auth_router.get("/me")
async def me(current_user=Depends(get_current_user)):
    return {
        "id": str(current_user.id),
        "email": current_user.email,
        "name": current_user.name,
    }
