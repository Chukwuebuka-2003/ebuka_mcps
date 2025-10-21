import uuid
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime
from fastapi.responses import StreamingResponse
from fastapi import Request, BackgroundTasks, HTTPException, UploadFile
import asyncio
from mcp_host.utils import call_mcp_server_tool
from mcp_host.models.chats import ChatSession, ChatMessage
from mcp_host.schemas.chats import (
    ChatSessionResponse,
    ChatMessageResponse,
    UploadMetadata,
)

import json
import logging

logger = logging.getLogger(__name__)


class ChatService:
    @staticmethod
    async def upload_student_file(
        request: Request,
        background_tasks: BackgroundTasks,
        meta: UploadMetadata,
        file: UploadFile,
    ):
        try:
            file_content = await file.read()
            if not file_content:
                raise HTTPException(status_code=400, detail="Uploaded file is empty")

            filename = file.filename or "unnamed_file"
            response = {
                "status": "success",
                "message": "File received; background processing started.",
            }

            background_tasks.add_task(
                ChatService._process_uploaded_file,
                request.app.state.storage_manager,
                request.app.state.agent_server.mcp_client,
                file_content,
                filename,
                file.content_type or "application/octet-stream",
                meta,
            )

            return response
        except Exception as e:
            logger.exception(f"Unexpected error during file upload: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")

    @staticmethod
    def _process_uploaded_file(
        storage_manager,
        mcp_client,
        file_content: bytes,
        filename: str,
        content_type: str,
        meta: UploadMetadata,
    ):
        try:
            upload_result = storage_manager.upload_file(
                file_content=file_content,
                student_id=meta.student_id,
                filename=filename,
                subject=meta.subject,
                metadata={
                    "topic": meta.topic,
                    "difficulty_level": str(meta.difficulty_level),
                    "content_type": content_type,
                },
            )

            if upload_result.get("status") != "success":
                logger.error(f"Background upload failed: {upload_result}")
                return

            mcp_sessions = getattr(mcp_client, "sessions", None)
            if not mcp_sessions:
                logger.error("MCP sessions not available")
                return

            asyncio.run(
                call_mcp_server_tool(
                    sessions=mcp_sessions,
                    server_name="TutoringRAGSystemMCPServer",
                    tool_name="upload_student_file",
                    tool_args={
                        "user_id": meta.student_id,
                        "filename": filename,
                        "file_id": upload_result["blob_name"],
                        "subject": meta.subject,
                        "topic": meta.topic,
                        "difficulty_level": meta.difficulty_level,
                    },
                )
            )
            logger.info(f"Completed background processing for {filename}")
        except Exception as e:
            logger.exception(f"Background task failed: {e}")

    @staticmethod
    async def chat_endpoint(
        request: Request, user_query: str, chat_session_id: str, current_user, db
    ):
        """Stream chat responses from the Tutor RAG Agent."""
        try:
            # Store the user query in the database
            metadata = {
                "chat_session_id": chat_session_id,
                "user_id": current_user.id,
            }
            await ChatService.store_chat_message(
                db=db,
                chat_session_id=chat_session_id,
                role="user",
                content=user_query,
                message_metadata=metadata,
            )
            result = await request.app.state.agent_server.handle_query(
                query=user_query,
                session_id=chat_session_id,
            )
            response = {
                "role": "assistant",
                "content": result["response"],
                "chat_session_id": result["session_id"],
            }
            # Store the assistant response in the database
            metadata = {
                "chat_session_id": chat_session_id,
                "user_id": current_user.id,
            }
            await ChatService.store_chat_message(
                db=db,
                chat_session_id=chat_session_id,
                role="assistant",
                content=result["response"],
                message_metadata=metadata,
            )
            yield json.dumps(response).encode("utf-8") + b"\n"
        except Exception as e:
            logger.error(f"Error in chat endpoint: {e}")
            yield (
                json.dumps(
                    {
                        "role": "assistant",
                        "content": f"Error processing query: {e}",
                        "chat_session_id": chat_session_id,
                    }
                ).encode("utf-8")
                + b"\n"
            )

    @staticmethod
    async def stream_events(request: Request, chat_session_id: str):
        """Stream real-time events for a session."""

        async def event_generator():
            try:
                async for event in request.app.state.agent_server.agent.stream_events(
                    session_id=chat_session_id
                ):
                    yield f"event: {event.type}\ndata: {event.json()}\n\n"
            except Exception as e:
                logger.error(f"Error streaming events: {e}")
                yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
        )

    @staticmethod
    async def get_session_history(request: Request, chat_session_id: str):
        try:
            history = await request.app.state.agent_server.get_session_history(
                session_id=chat_session_id
            )
            return {
                "status": "success",
                "chat_session_id": chat_session_id,
                "history": history,
                "message_count": len(history),
            }
        except Exception as e:
            logger.error(f"Error getting chat session history: {e}")
            return {"status": "error", "message": str(e)}

    @staticmethod
    async def clear_session_memory(request: Request, chat_session_id: str):
        try:
            success = await request.app.state.agent_server.clear_session_memory(
                session_id=chat_session_id
            )
            return {
                "status": "success" if success else "error",
                "message": "Memory cleared" if success else "Failed to clear memory",
            }
        except Exception as e:
            logger.error(f"Error clearing chat session memory: {e}")
            return {"status": "error", "message": str(e)}

    @staticmethod
    async def get_agent_info(request: Request):
        try:
            info = request.app.state.agent_server.get_agent_info()
            return {"status": "success", "agent_info": info}
        except Exception as e:
            logger.error(f"Error getting agent info: {e}")
            return {"status": "error", "message": str(e)}

    @staticmethod
    async def store_chat_message(
        db: AsyncSession,
        chat_session_id: str,
        role: str,
        content: str,
        message_metadata: dict = None,
    ) -> ChatMessage:
        """Store a chat message in the database."""
        message = ChatMessage(
            chat_session_id=chat_session_id,
            role=role,
            content=content,
            message_metadata=message_metadata or {},
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        db.add(message)
        await db.commit()
        await db.refresh(message)
        return message

    @staticmethod
    async def get_or_create_chat(
        current_user,
        request_messages: list,
        db: AsyncSession,
        chat_session_id: Optional[str] = None,
    ) -> Optional[str]:
        """Get existing chat or create new one if chat_session_id is None or not found."""
        if chat_session_id:
            # Try to get existing chat
            chat_session = await db.execute(
                select(ChatSession).where(
                    ChatSession.chat_session_id == chat_session_id,
                    ChatSession.user_id == current_user.id,
                )
            )
            chat_session = chat_session.scalar_one_or_none()
            if chat_session:
                return chat_session.chat_session_id
        else:
            # Create new chat
            first_user_message = next(
                (msg.content for msg in request_messages if msg.role == "user"),
                "Untitled Chat",
            )
            new_chat_session_id = str(uuid.uuid4())
            chat_session = ChatSession(
                chat_session_id=new_chat_session_id,
                user_id=current_user.id,
                title=first_user_message[:20],
            )
            db.add(chat_session)
            await db.commit()
            await db.refresh(chat_session)
            return chat_session.chat_session_id

    @staticmethod
    async def update_chat_title(
        current_user, chat_session_id: str, title: str, db: AsyncSession
    ) -> Optional[ChatSessionResponse]:
        """Update the title of a chat."""
        chat_session = await db.execute(
            select(ChatSession).where(
                ChatSession.chat_session_id == chat_session_id,
                ChatSession.user_id == current_user.id,
            )
        )
        chat_session = chat_session.scalar_one_or_none()
        if not chat_session:
            return None

        chat_session.title = title
        chat_session.updated_at = datetime.now()
        await db.commit()
        await db.refresh(chat_session)
        return ChatSessionResponse.model_validate(chat_session)

    @staticmethod
    async def delete_chat(current_user, chat_session_id: str, db: AsyncSession) -> dict:
        """Delete a chat."""
        chat_session = await db.execute(
            select(ChatSession).where(
                ChatSession.chat_session_id == chat_session_id,
                ChatSession.user_id == current_user.id,
            )
        )
        chat_session = chat_session.scalar_one_or_none()
        if not chat_session:
            return {"message": "Chat not found"}
        await db.delete(chat_session)
        await db.commit()
        return {"message": "Chat deleted successfully"}

    @staticmethod
    async def get_chat_by_id(
        current_user, chat_session_id: str, db: AsyncSession
    ) -> ChatSessionResponse:
        """Get a chat by id."""
        chat_session = await db.execute(
            select(ChatSession).where(
                ChatSession.chat_session_id == chat_session_id,
                ChatSession.user_id == current_user.id,
            )
        )
        chat_session = chat_session.scalar_one_or_none()
        if not chat_session:
            return {"message": "Chat not found"}
        return ChatSessionResponse.model_validate(chat_session)

    @staticmethod
    async def get_chat_conversation(
        current_user, chat_session_id: str, db: AsyncSession
    ) -> list:
        """Get all messages in a chat (conversation)."""
        # Ensure the chat belongs to the user
        chat = await db.execute(
            select(ChatSession).where(
                ChatSession.chat_session_id == chat_session_id,
                ChatSession.user_id == current_user.id,
            )
        )
        chat = chat.scalar_one_or_none()
        if not chat:
            return None

        result = await db.execute(
            select(ChatMessage)
            .where(ChatMessage.chat_session_id == chat_session_id)
            .order_by(ChatMessage.created_at.asc())
        )
        messages = result.scalars().all()
        return [ChatMessageResponse.model_validate(msg) for msg in messages]

    @staticmethod
    async def get_user_chats(current_user, db: AsyncSession) -> list:
        """Get all chat sessions for a user."""
        result = await db.execute(
            select(ChatSession)
            .where(ChatSession.user_id == current_user.id)
            .order_by(ChatSession.updated_at.desc())
        )
        chats = result.scalars().all()
        return [ChatSessionResponse.model_validate(chat) for chat in chats]
