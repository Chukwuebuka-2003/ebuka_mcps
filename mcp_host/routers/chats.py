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
    FileUploadStatusResponse,
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
    db: AsyncSession = Depends(get_db),
):
    """Upload a student file with metadata, process in background."""
    logger.info(f"📤 File upload request received: {file.filename}")
    return await ChatService.upload_student_file(request, background_tasks, meta, file, db)


@chat_router.get("/files/{file_id}/status", response_model=FileUploadStatusResponse)
async def get_file_upload_status(
    file_id: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Check the status of an uploaded file."""
    logger.info(f"🔍 File status request for: {file_id}")
    return await ChatService.get_file_upload_status(db, file_id, str(current_user.id))


@chat_router.get("/events/{chat_session_id}")
async def stream_events(
    request: Request, chat_session_id: str, current_user=Depends(get_current_user)
):
    """Stream events for a specific session."""
    logger.info(f"📡 Event stream request for session: {chat_session_id}")
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

    # ==================== DETAILED LOGGING ====================
    logger.info("=" * 80)
    logger.info("💬 CHAT REQUEST RECEIVED")
    logger.info("=" * 80)
    logger.info(f"📋 Request Details:")
    logger.info(f"  - User ID: {current_user.id}")
    logger.info(f"  - User Email: {current_user.email}")
    logger.info(f"  - Session ID: {chat_message_request.chat_session_id}")
    logger.info(f"  - Message Count: {len(chat_message_request.messages)}")
    logger.info(
        f"  - Client IP: {request.client.host if request.client else 'unknown'}"
    )

    # Log all messages
    for i, msg in enumerate(chat_message_request.messages):
        logger.info(f"  - Message {i + 1}: [{msg.role}] {msg.content[:100]}...")

    logger.info("=" * 80)
    # =========================================================

    try:
        chat_session_id = chat_message_request.chat_session_id

        logger.info("🔄 Getting or creating chat session...")
        get_chat_session_id = await ChatService.get_or_create_chat(
            current_user=current_user,
            request_messages=getattr(chat_message_request, "messages", None),
            chat_session_id=chat_session_id,
            db=db,
        )
        logger.info(f"✅ Chat session ID: {get_chat_session_id}")

        user_query = chat_message_request.messages[-1].content
        file_id = chat_message_request.messages[-1].file_id
        logger.info(f"📝 Processing query: '{user_query[:100]}...'")
        if file_id:
            logger.info(f"📎 File attached: {file_id}")

        return StreamingResponse(
            ChatService.chat_endpoint(
                request=request,
                user_query=user_query,
                chat_session_id=get_chat_session_id,
                current_user=current_user,
                db=db,
                file_id=file_id,
            ),
            media_type="text/plain",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
        )
    except Exception as e:
        logger.error("=" * 80)
        logger.error("❌ CHAT REQUEST FAILED")
        logger.error(f"Error: {str(e)}")
        logger.error("=" * 80)
        logger.exception(e)
        raise


@chat_router.get("/session/{chat_session_id}/history")
async def get_session_history(
    request: Request, chat_session_id: str, current_user=Depends(get_current_user)
):
    """Fetch session history."""
    logger.info(f"📜 Session history request for: {chat_session_id}")
    return await ChatService.get_session_history(
        request=request, chat_session_id=chat_session_id
    )


@chat_router.delete("/session/{chat_session_id}/memory")
async def clear_session_memory(
    request: Request, chat_session_id: str, current_user=Depends(get_current_user)
):
    """Clear memory for a session."""
    logger.info(f"🗑️  Clear memory request for session: {chat_session_id}")
    return await ChatService.clear_session_memory(
        request=request, chat_session_id=chat_session_id
    )


@chat_router.get("/agent/info")
async def get_agent_info(request: Request, current_user=Depends(get_current_user)):
    """Return info about current agent configuration."""
    logger.info("ℹ️  Agent info request")
    return await ChatService.get_agent_info(request=request)


@chat_router.put("/{chat_session_id}/title", response_model=ChatSessionResponse)
async def update_chat_title(
    chat_session_id: str,
    title_request: UpdateChatTitleRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update the title of a chat."""
    logger.info(f"✏️  Update title request for session: {chat_session_id}")
    try:
        result = await ChatService.update_chat_title(
            current_user, chat_session_id, title_request.title, db
        )
        if not result:
            raise HTTPException(status_code=404, detail="Chat not found")
        logger.info(f"✅ Title updated successfully")
        return result
    except Exception as e:
        logger.error(f"❌ Failed to update chat title: {str(e)}")
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
    logger.info(f"🗑️  Delete chat request for session: {chat_session_id}")
    try:
        result = await ChatService.delete_chat(current_user, chat_session_id, db)
        if result.get("message") == "Chat not found":
            raise HTTPException(status_code=404, detail="Chat not found")
        logger.info(f"✅ Chat deleted successfully")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to delete chat: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to delete chat: {str(e)}")


@chat_router.get("/{chat_session_id}", response_model=ChatSessionResponse)
async def get_chat_by_id(
    chat_session_id: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a chat by id."""
    logger.info(f"🔍 Get chat by ID request: {chat_session_id}")
    try:
        result = await ChatService.get_chat_by_id(current_user, chat_session_id, db)
        if isinstance(result, dict) and result.get("message") == "Chat not found":
            raise HTTPException(status_code=404, detail="Chat not found")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to get chat: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get chat: {str(e)}")


@chat_router.get("/", response_model=List[ChatSessionResponse])
async def get_user_chats(
    current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """Get all chat sessions for the current user."""
    logger.info(f"📚 Get all chats request for user: {current_user.id}")
    try:
        chats = await ChatService.get_user_chats(current_user=current_user, db=db)
        logger.info(f"✅ Found {len(chats)} chats")
        return chats
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to get user chats: {str(e)}")
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
    logger.info(f"💬 Get conversation history for session: {chat_session_id}")
    try:
        messages = await ChatService.get_chat_conversation(
            current_user=current_user, chat_session_id=chat_session_id, db=db
        )
        if messages is None:
            raise HTTPException(status_code=404, detail="Chat not found")
        logger.info(f"✅ Found {len(messages)} messages")
        return messages
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to get chat conversation: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to get chat conversation: {str(e)}"
        )

