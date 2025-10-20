from pydantic import BaseModel, Field
from enum import Enum
from typing import Optional, List


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


# Chat Request/Response Schemas
class MessageSchema(BaseModel):
    role: MessageRole
    content: str


class ChatMessageRequest(BaseModel):
    messages: List[MessageSchema]
    session_id: Optional[str] = None


class UploadMetadata(BaseModel):
    student_id: str
    subject: str
    topic: str
    difficulty_level: int = Field(
        ge=1, le=10, description="Level from 1 (easy) to 10 (hard)"
    )
