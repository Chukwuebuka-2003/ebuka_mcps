import json
import uuid
from fastapi import (
    File,
    UploadFile,
    HTTPException,
    Request,
    Depends,
    BackgroundTasks,
    APIRouter,
    Depends,
)
from fastapi.responses import StreamingResponse
from mcp_host.schemas.chats import (
    ChatMessageRequest,
    UploadMetadata,
    ChatSessionResponse,
    UpdateChatTitleRequest,
    ChatMessageResponse,
)
from mcp_host.utils import parse_upload_metadata
from mcp_host.services.chats import ChatService
from mcp_host.database.db import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from mcp_host.services.auths import get_current_user
import logging


logger = logging.getLogger(__name__)

chat_router = APIRouter()


@chat_router.post("/upload-student-file")
async def upload_student_file(
    request: Request,
    background_tasks: BackgroundTasks,
    meta: UploadMetadata = Depends(parse_upload_metadata),
    file: UploadFile = File(...),
):
    """Upload a student file with metadata, process in background."""
    return await ChatService.upload_student_file(request, background_tasks, meta, file)


@chat_router.get("/events/{chat_session_id}")
async def stream_events(
    request: Request, chat_session_id: str, current_user=Depends(get_current_user)
):
    """Stream events for a specific session."""
    return await ChatService.stream_events(
        request=request, chat_session_id=chat_session_id
    )


@chat_router.post("/tutor-rag-agent")
async def chat(
    request: Request,
    chat_message_request: ChatMessageRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Stream chat responses from the Tutor RAG Agent."""
    chat_session_id = chat_message_request.chat_session_id
    get_chat_session_id = await ChatService.get_or_create_chat(
        current_user=current_user,
        request_messages=getattr(chat_message_request, "messages", None),
        chat_session_id=chat_session_id,
        db=db,
    )

    user_query = chat_message_request.messages[-1].content
    return StreamingResponse(
        ChatService.chat_endpoint(
            request=request,
            user_query=user_query,
            chat_session_id=get_chat_session_id,
            current_user=current_user,
            db=db,
        ),
        media_type="text/plain",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@chat_router.get("/session/{chat_session_id}/history")
async def get_session_history(
    request: Request, chat_session_id: str, current_user=Depends(get_current_user)
):
    """Fetch session history."""
    return await ChatService.get_session_history(
        request=request, chat_session_id=chat_session_id
    )


@chat_router.delete("/session/{chat_session_id}/memory")
async def clear_session_memory(
    request: Request, chat_session_id: str, current_user=Depends(get_current_user)
):
    """Clear memory for a session."""
    return await ChatService.clear_session_memory(
        request=request, chat_session_id=chat_session_id
    )


@chat_router.get("/agent/info")
async def get_agent_info(request: Request, current_user=Depends(get_current_user)):
    """Return info about current agent configuration."""
    return await ChatService.get_agent_info(request=request)


@chat_router.put("/{chat_session_id}/title", response_model=ChatSessionResponse)
async def update_chat_title(
    chat_session_id: str,
    title_request: UpdateChatTitleRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update the title of a chat."""
    try:
        result = await ChatService.update_chat_title(
            current_user, chat_session_id, title_request.title, db
        )
        if not result:
            raise HTTPException(status_code=404, detail="Chat not found")
        return result
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to update chat title: {str(e)}"
        )


@chat_router.delete("/{chat_session_id}")
async def delete_chat(
    chat_session_id: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a chat."""
    try:
        result = await ChatService.delete_chat(current_user, chat_session_id, db)
        if result.get("message") == "Chat not found":
            raise HTTPException(status_code=404, detail="Chat not found")
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete chat: {str(e)}")


@chat_router.get("/{chat_session_id}", response_model=ChatSessionResponse)
async def get_chat_by_id(
    chat_session_id: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a chat by id."""
    try:
        result = await ChatService.get_chat_by_id(current_user, chat_session_id, db)
        if isinstance(result, dict) and result.get("message") == "Chat not found":
            raise HTTPException(status_code=404, detail="Chat not found")
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get chat: {str(e)}")


@chat_router.get("/", response_model=List[ChatSessionResponse])
async def get_user_chats(
    current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """Get all chat sessions for the current user."""
    try:
        chats = await ChatService.get_user_chats(current_user=current_user, db=db)
        return chats
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to get user chats: {str(e)}"
        )


@chat_router.get("/{chat_session_id}/history", response_model=List[ChatMessageResponse])
async def get_chat_conversation(
    chat_session_id: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get all messages in a chat (conversation)."""
    try:
        messages = await ChatService.get_chat_conversation(
            current_user=current_user, chat_session_id=chat_session_id, db=db
        )
        if messages is None:
            raise HTTPException(status_code=404, detail="Chat not found")
        return messages
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to get chat conversation: {str(e)}"
        )
