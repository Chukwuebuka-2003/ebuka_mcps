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
    file_id: Optional[str] = Field(
        None, description="File ID to associate with this message for tracking uploaded files"
    )


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
    upload_date: Optional[datetime] = Field(
        None, description="Custom upload date (defaults to current time if not provided)"
    )  # NEW: Custom upload date field
    chat_session_id: Optional[str] = Field(
        None, description="Chat session ID to link this upload to a conversation"
    )  # NEW: Link upload to chat session


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


# File Upload Status Schemas
class FileUploadStatusEnum(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class FileUploadStatusResponse(BaseModel):
    id: str
    filename: str
    subject: str
    topic: str
    status: FileUploadStatusEnum
    chunks_processed: int
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
