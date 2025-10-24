from pydantic import BaseModel, Field
from enum import Enum
from typing import Optional, List
from datetime import datetime


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
    chat_session_id: Optional[str] = None


class UploadMetadata(BaseModel):
    student_id: str
    subject: str
    topic: str
    difficulty_level: int = Field(
        ge=1, le=10, description="Level from 1 (easy) to 10 (hard)"
    )
    document_title: Optional[str] = Field(
        None, description="Custom document title for citations"
    )  # NEW: Document title field


# Chat Session Schemas
class ChatSessionBase(BaseModel):
    user_id: Optional[str] = None
    title: Optional[str] = None


class ChatSessionCreate(ChatSessionBase):
    pass


class ChatMessageResponse(BaseModel):
    role: str
    content: str
    message_metadata: Optional[dict] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ChatResponse(BaseModel):
    chat_session_id: str
    message: ChatMessageResponse


class ChatSessionResponse(ChatSessionBase):
    id: int
    chat_session_id: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# List Response Schemas
class ChatHistoryResponse(BaseModel):
    messages: List[ChatMessageResponse]
    total: int


class UpdateChatTitleRequest(BaseModel):
    title: str = Field(..., min_length=1)
