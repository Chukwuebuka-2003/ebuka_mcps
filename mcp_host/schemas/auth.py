from pydantic import BaseModel, Field


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
