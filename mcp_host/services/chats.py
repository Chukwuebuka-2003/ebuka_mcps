import uuid
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone
from fastapi.responses import StreamingResponse
from fastapi import Request, BackgroundTasks, HTTPException, UploadFile
import asyncio
from mcp_host.utils import call_mcp_server_tool
from mcp_host.models.chats import ChatSession, ChatMessage, FileUpload, FileUploadStatus
from mcp_host.schemas.chats import (
    ChatSessionResponse,
    ChatMessageResponse,
    UploadMetadata,
)
from mcp_host.database.db import get_db_session, SyncSessionLocal
from mcp_host.services.session_tracker import SessionTracker

import json
import logging
import re

logger = logging.getLogger(__name__)


class ChatService:
    @staticmethod
    def _extract_subject_and_topic(query: str, response: str) -> tuple[str, str, int]:
        """
        Extract subject, topic, and difficulty from user query and AI response.
        Returns: (subject, topic, difficulty_level)
        """
        # Common subjects
        subjects_map = {
            'math': ['calculus', 'algebra', 'geometry', 'trigonometry', 'statistics', 'arithmetic'],
            'physics': ['mechanics', 'thermodynamics', 'electromagnetism', 'quantum', 'optics'],
            'chemistry': ['organic', 'inorganic', 'physical chemistry', 'biochemistry'],
            'biology': ['cell', 'genetics', 'evolution', 'ecology', 'anatomy'],
            'computer science': ['programming', 'algorithm', 'data structure', 'database', 'python', 'javascript'],
            'english': ['grammar', 'writing', 'literature', 'essay', 'vocabulary'],
            'history': ['ancient', 'medieval', 'modern', 'world war', 'revolution'],
        }

        query_lower = query.lower()
        response_lower = response.lower()
        combined = query_lower + " " + response_lower

        # Detect subject
        detected_subject = "General"
        for subject, keywords in subjects_map.items():
            for keyword in keywords:
                if keyword in combined:
                    detected_subject = subject.title()
                    break
            if detected_subject != "General":
                break

        # Extract topic (use first sentence or key phrase from query)
        topic = query[:100] if len(query) <= 100 else query[:97] + "..."

        # Estimate difficulty based on query complexity
        difficulty_indicators = {
            'advanced': 8, 'complex': 7, 'difficult': 7,
            'intermediate': 5, 'basic': 3, 'simple': 2,
            'beginner': 2, 'intro': 3, 'fundamental': 4
        }

        difficulty = 5  # Default medium difficulty
        for indicator, level in difficulty_indicators.items():
            if indicator in query_lower:
                difficulty = level
                break

        return detected_subject, topic, difficulty

    @staticmethod
    async def upload_student_file(
        request: Request,
        background_tasks: BackgroundTasks,
        meta: UploadMetadata,
        file: UploadFile,
        db: AsyncSession,
    ):
        try:
            file_content = await file.read()
            if not file_content:
                raise HTTPException(status_code=400, detail="Uploaded file is empty")

            filename = file.filename or "unnamed_file"

            # Check if agent server and mcp_client are available
            if not hasattr(request.app.state, 'agent_server'):
                raise HTTPException(status_code=503, detail="Agent server not initialized")

            if not hasattr(request.app.state.agent_server, 'mcp_client') or not request.app.state.agent_server.mcp_client:
                raise HTTPException(status_code=503, detail="MCP client not initialized")

            # Create file upload tracking record
            file_id = str(uuid.uuid4())
            file_upload = FileUpload(
                id=file_id,
                user_id=meta.student_id,
                filename=filename,
                subject=meta.subject,
                topic=meta.topic,
                status=FileUploadStatus.PENDING,
            )
            db.add(file_upload)
            await db.commit()
            await db.refresh(file_upload)

            response = {
                "status": "success",
                "message": "File received; background processing started.",
                "file_id": file_id,
            }

            background_tasks.add_task(
                ChatService._process_uploaded_file,
                request.app.state.storage_manager,
                request.app.state.agent_server.mcp_client,
                file_content,
                filename,
                file.content_type or "application/octet-stream",
                meta,
                file_id,
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
        file_id: str,
    ):
        def update_status(status: FileUploadStatus, blob_name: str = None, error_msg: str = None):
            """Update file upload status using synchronous database session"""
            db = SyncSessionLocal()
            try:
                file_record = db.query(FileUpload).filter(FileUpload.id == file_id).first()
                if file_record:
                    file_record.status = status
                    file_record.updated_at = datetime.now(timezone.utc)
                    if blob_name:
                        file_record.blob_name = blob_name
                    if error_msg:
                        file_record.error_message = error_msg
                    db.commit()
            except Exception as e:
                logger.error(f"Failed to update file status: {e}")
                db.rollback()
            finally:
                db.close()

        try:
            # Update status to PROCESSING
            update_status(FileUploadStatus.PROCESSING)

            upload_result = storage_manager.upload_file(
                file_content=file_content,
                student_id=meta.student_id,
                filename=filename,
                subject=meta.subject,
                metadata={
                    "topic": meta.topic,
                    "difficulty_level": str(meta.difficulty_level),
                    "content_type": content_type,
                    "document_title": meta.document_title,
                },
            )

            if upload_result.get("status") != "success":
                error_msg = f"Background upload failed: {upload_result}"
                logger.error(error_msg)
                update_status(FileUploadStatus.FAILED, error_msg=error_msg)
                return

            blob_name = upload_result["blob_name"]

            # Check if mcp_client exists and has sessions
            if not mcp_client:
                error_msg = "MCP client not available"
                logger.error(error_msg)
                update_status(FileUploadStatus.FAILED, blob_name=blob_name, error_msg=error_msg)
                return

            mcp_sessions = getattr(mcp_client, "sessions", None)
            if not mcp_sessions:
                error_msg = "MCP sessions not available - client may not be fully initialized"
                logger.error(error_msg)
                logger.error(f"MCP client type: {type(mcp_client)}")
                logger.error(f"MCP sessions value: {mcp_sessions}")
                logger.error(f"MCP sessions type: {type(mcp_sessions)}")
                update_status(FileUploadStatus.FAILED, blob_name=blob_name, error_msg=error_msg)
                return

            # Check if the required server exists in sessions
            server_name = "TutoringRAGSystemMCPServer"
            if server_name not in mcp_sessions:
                available_servers = list(mcp_sessions.keys()) if mcp_sessions else []
                error_msg = f"Server '{server_name}' not found in MCP sessions. Available: {available_servers}"
                logger.error(error_msg)
                update_status(FileUploadStatus.FAILED, blob_name=blob_name, error_msg=error_msg)
                return

            asyncio.run(
                call_mcp_server_tool(
                    sessions=mcp_sessions,
                    server_name=server_name,
                    tool_name="upload_student_file",
                    tool_args={
                        "user_id": meta.student_id,
                        "filename": filename,
                        "file_id": blob_name,
                        "subject": meta.subject,
                        "topic": meta.topic,
                        "difficulty_level": meta.difficulty_level,
                        "document_title": meta.document_title,
                    },
                )
            )

            # Update status to COMPLETED
            update_status(FileUploadStatus.COMPLETED, blob_name=blob_name)
            logger.info(f"Completed background processing for {filename}")

            # Track file upload as a learning session
            try:
                from uuid import UUID
                user_uuid = UUID(meta.student_id) if isinstance(meta.student_id, str) else meta.student_id
                sync_db = SyncSessionLocal()
                try:
                    import asyncio
                    asyncio.run(SessionTracker.track_file_upload(
                        db=sync_db,
                        user_id=user_uuid,
                        subject=meta.subject,
                        topic=meta.topic,
                        filename=filename
                    ))
                    logger.info(f"📁 File upload session tracked for {filename}")
                finally:
                    sync_db.close()
            except Exception as e:
                logger.error(f"Failed to track file upload session: {e}")
        except Exception as e:
            error_msg = f"Background task failed: {e}"
            logger.exception(error_msg)
            update_status(FileUploadStatus.FAILED, error_msg=error_msg)

    @staticmethod
    async def chat_endpoint(
        request: Request, user_query: str, chat_session_id: str, current_user, db
    ):
        """Stream chat responses from the Tutor RAG Agent."""
        try:
            logger.info(f"Processing query: {user_query[:50]}...")

            # Store the user query in the database
            metadata = {
                "chat_session_id": chat_session_id,
                "user_id": str(current_user.id),
            }

            try:
                await ChatService.store_chat_message(
                    db=db,
                    chat_session_id=chat_session_id,
                    role="user",
                    content=user_query,
                    message_metadata=metadata,
                )
                logger.info("User message stored successfully")
            except Exception as e:
                logger.error(f"Failed to store user message: {e}")

            # ============= FIX: Pass user context to agent =============
            user_context = {
                "user_id": str(current_user.id),
                "email": current_user.email,
                "name": current_user.name,
            }
            logger.info(f"Passing user context to agent: {user_context}")
            # ===========================================================

            # Call agent with timeout
            logger.info("Calling agent...")
            try:
                result = await asyncio.wait_for(
                    request.app.state.agent_server.handle_query(
                        query=user_query,
                        session_id=chat_session_id,
                        user_context=user_context,  # FIX: Pass user context
                    ),
                    timeout=60.0,
                )
                logger.info("Agent response received")
            except asyncio.TimeoutError:
                logger.error("Agent query timed out")
                result = {
                    "response": "I apologize, but the request timed out. Please try again.",
                    "session_id": chat_session_id,
                }
            except Exception as e:
                logger.error(f"Agent error: {e}", exc_info=True)
                result = {
                    "response": f"An error occurred: {str(e)}",
                    "session_id": chat_session_id,
                }

            response = {
                "role": "assistant",
                "content": result["response"],
                "chat_session_id": result["session_id"],
            }

            # Store the assistant response in the database
            try:
                await ChatService.store_chat_message(
                    db=db,
                    chat_session_id=chat_session_id,
                    role="assistant",
                    content=result["response"],
                    message_metadata=metadata,
                )
                logger.info("Assistant message stored successfully")
            except Exception as e:
                logger.error(f"Failed to store assistant message: {e}")

            # Track learning session for progress reporting
            try:
                subject, topic, difficulty = ChatService._extract_subject_and_topic(
                    user_query, result["response"]
                )
                await SessionTracker.track_chat_session(
                    db=db,
                    user_id=current_user.id,
                    subject=subject,
                    topic=topic,
                    difficulty_level=difficulty,
                    questions_asked=1
                )
                logger.info(f"📊 Session tracked: {subject}/{topic}")
            except Exception as e:
                logger.error(f"Failed to track session: {e}")
                # Don't break chat if tracking fails

            logger.info("Sending response to client")
            yield json.dumps(response).encode("utf-8") + b"\n"

        except Exception as e:
            logger.error(f"Error in chat endpoint: {e}", exc_info=True)
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
    async def get_file_upload_status(db: AsyncSession, file_id: str, user_id: str):
        """Get the status of a file upload."""
        result = await db.execute(
            select(FileUpload).where(
                FileUpload.id == file_id,
                FileUpload.user_id == user_id
            )
        )
        file_record = result.scalar_one_or_none()
        if not file_record:
            raise HTTPException(
                status_code=404,
                detail="File upload record not found or access denied"
            )
        return file_record

    @staticmethod
    async def store_chat_message(
        db: AsyncSession,
        chat_session_id: str,
        role: str,
        content: str,
        message_metadata: dict = None,
    ) -> ChatMessage:
        """Store a chat message in the database."""
        try:
            message = ChatMessage(
                chat_session_id=chat_session_id,
                role=role,
                content=content,
                message_metadata=message_metadata or {},
                created_at=datetime.now(),
                updated_at=datetime.now(),
            )
            db.add(message)
            await db.flush()
            await db.refresh(message)
            return message
        except Exception as e:
            logger.error(f"Error storing chat message: {e}")
            raise

    @staticmethod
    async def get_or_create_chat(
        current_user,
        request_messages: list,
        db: AsyncSession,
        chat_session_id: Optional[str] = None,
    ) -> Optional[str]:
        """Get existing chat or create new one if chat_session_id is None or not found."""
        try:
            user_id_str = str(current_user.id)

            if chat_session_id:
                result = await db.execute(
                    select(ChatSession).where(
                        ChatSession.chat_session_id == chat_session_id,
                        ChatSession.user_id == user_id_str,
                    )
                )
                chat_session = result.scalar_one_or_none()
                if chat_session:
                    return chat_session.chat_session_id

            # Create new chat
            first_user_message = next(
                (msg.content for msg in request_messages if msg.role == "user"),
                "Untitled Chat",
            )
            new_chat_session_id = str(uuid.uuid4())
            chat_session = ChatSession(
                chat_session_id=new_chat_session_id,
                user_id=user_id_str,
                title=first_user_message[:20],
            )
            db.add(chat_session)
            await db.flush()
            await db.refresh(chat_session)
            return chat_session.chat_session_id
        except Exception as e:
            logger.error(f"Error in get_or_create_chat: {e}")
            raise

    @staticmethod
    async def update_chat_title(
        current_user, chat_session_id: str, title: str, db: AsyncSession
    ) -> Optional[ChatSessionResponse]:
        """Update the title of a chat."""
        user_id_str = str(current_user.id)

        result = await db.execute(
            select(ChatSession).where(
                ChatSession.chat_session_id == chat_session_id,
                ChatSession.user_id == user_id_str,
            )
        )
        chat_session = result.scalar_one_or_none()
        if not chat_session:
            return None

        chat_session.title = title
        chat_session.updated_at = datetime.now()
        await db.flush()
        await db.refresh(chat_session)
        return ChatSessionResponse.model_validate(chat_session)

    @staticmethod
    async def delete_chat(current_user, chat_session_id: str, db: AsyncSession) -> dict:
        """Delete a chat."""
        user_id_str = str(current_user.id)

        result = await db.execute(
            select(ChatSession).where(
                ChatSession.chat_session_id == chat_session_id,
                ChatSession.user_id == user_id_str,
            )
        )
        chat_session = result.scalar_one_or_none()
        if not chat_session:
            return {"message": "Chat not found"}
        await db.delete(chat_session)
        await db.flush()
        return {"message": "Chat deleted successfully"}

    @staticmethod
    async def get_chat_by_id(
        current_user, chat_session_id: str, db: AsyncSession
    ) -> ChatSessionResponse:
        """Get a chat by id."""
        user_id_str = str(current_user.id)

        result = await db.execute(
            select(ChatSession).where(
                ChatSession.chat_session_id == chat_session_id,
                ChatSession.user_id == user_id_str,
            )
        )
        chat_session = result.scalar_one_or_none()
        if not chat_session:
            return {"message": "Chat not found"}
        return ChatSessionResponse.model_validate(chat_session)

    @staticmethod
    async def get_chat_conversation(
        current_user, chat_session_id: str, db: AsyncSession
    ) -> list:
        """Get all messages in a chat (conversation)."""
        user_id_str = str(current_user.id)

        # Ensure the chat belongs to the user
        result = await db.execute(
            select(ChatSession).where(
                ChatSession.chat_session_id == chat_session_id,
                ChatSession.user_id == user_id_str,
            )
        )
        chat = result.scalar_one_or_none()
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
        user_id_str = str(current_user.id)

        result = await db.execute(
            select(ChatSession)
            .where(ChatSession.user_id == user_id_str)
            .order_by(ChatSession.updated_at.desc())
        )
        chats = result.scalars().all()
        return [ChatSessionResponse.model_validate(chat) for chat in chats]
