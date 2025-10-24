from pydantic import BaseModel, Field, ConfigDict
from uuid import UUID
from datetime import time, datetime
from typing import Optional



class UserCreate(BaseModel):
    name: str = Field(..., description="The name of the user")
    email: Optional[str] = Field(default=None, description="The email of the user")
    phone_number: str = Field(..., description="The phone number of the user")
    


class UserResponse(BaseModel):
    id: UUID = Field(..., description="The ID of the user")
    name: str = Field(..., description="The name of the user")
    email: Optional[str] = Field(default=None, description="The email of the user")
    phone_number: str = Field(..., description="The phone number of the user")
    created_at: Optional[datetime] = Field(
        default=None, description="The creation date of the user"
    )
    updated_at: Optional[datetime] = Field(
        default=None, description="The last update date of the user"
    )

    model_config = ConfigDict(from_attributes=True)


class UserUpdate(BaseModel):
    name: Optional[str] = Field(default=None, description="The name of the user")
    email: Optional[str] = Field(default=None, description="The email of the user")
    