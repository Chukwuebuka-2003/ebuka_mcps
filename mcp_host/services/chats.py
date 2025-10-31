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
import os
from openai import OpenAI

logger = logging.getLogger(__name__)

# Initialize OpenAI client for subject detection
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


class ChatService:
    @staticmethod
    def _ai_detect_subject(text: str, context: str = "chat") -> str:
        """
        Use AI to intelligently detect the subject from text content.

        Args:
            text: The text to analyze (query, response, or document content)
            context: Either "chat" or "document" to provide better context

        Returns:
            Detected subject name (e.g., "Mathematics", "Physics", "Computer Science")
        """
        try:
            prompt = f"""Analyze the following {context} content and identify the primary academic subject.

Content: {text[:1500]}

Return ONLY the subject name from this list:
- Mathematics
- Physics
- Chemistry
- Biology
- Computer Science
- English
- History
- Geography
- Economics
- Psychology
- Philosophy
- Art
- Music
- Engineering
- Business
- General

If the content clearly fits multiple subjects, choose the most dominant one.
If unclear, return "General".

Subject:"""

            response = openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are an expert at identifying academic subjects from content. Always respond with a single subject name."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=20
            )

            detected_subject = response.choices[0].message.content.strip()
            logger.info(f"🤖 AI detected subject: {detected_subject}")
            return detected_subject

        except Exception as e:
            logger.error(f"AI subject detection failed: {e}")
            return "General"

    @staticmethod
    def _extract_subject_and_topic(query: str, response: str) -> tuple[str, str, int]:
        """
        Extract subject, topic, and difficulty from user query and AI response.
        Uses AI-powered detection for accurate subject identification.
        Returns: (subject, topic, difficulty_level)
        """
        # Use AI to detect subject from combined query and response
        combined_text = f"Question: {query}\n\nAnswer: {response}"
        detected_subject = ChatService._ai_detect_subject(combined_text, context="chat")

        # Extract topic (use first sentence or key phrase from query)
        topic = query[:100] if len(query) <= 100 else query[:97] + "..."

        # Estimate difficulty based on query complexity
        query_lower = query.lower()
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

            # Use custom upload_date if provided, otherwise use current time
            upload_timestamp = meta.upload_date if meta.upload_date else datetime.now(timezone.utc)

            file_upload = FileUpload(
                id=file_id,
                user_id=meta.student_id,
                filename=filename,
                subject=meta.subject,
                topic=meta.topic,
                status=FileUploadStatus.PENDING,
                created_at=upload_timestamp,  # Use custom or current date
            )
            db.add(file_upload)
            await db.commit()
            await db.refresh(file_upload)

            response = {
                "status": "success",
                "message": "File received; background processing started.",
                "file_id": file_id,
                "document_info": {
                    "filename": filename,
                    "document_title": meta.document_title or filename,
                    "subject": meta.subject,
                    "topic": meta.topic,
                    "upload_date": upload_timestamp.isoformat(),
                }
            }

            # If a chat_session_id is provided, store the file upload event in chat history
            if meta.chat_session_id:
                try:
                    document_title = meta.document_title or filename
                    upload_message = f"📄 Document uploaded: {document_title}"

                    upload_metadata = {
                        "event_type": "file_upload",
                        "file_id": file_id,
                        "filename": filename,
                        "document_title": document_title,
                        "subject": meta.subject,
                        "topic": meta.topic,
                        "upload_date": upload_timestamp.isoformat(),
                    }

                    await ChatService.store_chat_message(
                        db=db,
                        chat_session_id=meta.chat_session_id,
                        role="system",
                        content=upload_message,
                        message_metadata=upload_metadata,
                    )
                    logger.info(f"📝 File upload event stored in chat history: {meta.chat_session_id}")
                except Exception as e:
                    logger.error(f"Failed to store file upload in chat history: {e}")
                    # Don't fail the upload if chat history storage fails

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
            # Note: Background task runs in a thread pool, use asyncio.run for async code
            try:
                from uuid import UUID
                user_uuid = UUID(meta.student_id) if isinstance(meta.student_id, str) else meta.student_id

                # Create new event loop for background task
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    # Use synchronous session for background task
                    from mcp_host.database.db import get_sync_db
                    sync_db = next(get_sync_db())

                    # Convert AsyncSession method to work with sync session
                    loop.run_until_complete(SessionTracker.track_file_upload(
                        db=sync_db,
                        user_id=user_uuid,
                        subject=meta.subject,
                        topic=meta.topic,
                        filename=filename
                    ))
                    logger.info(f"📁 File upload session tracked for {filename}")
                finally:
                    loop.close()
            except Exception as e:
                logger.error(f"Failed to track file upload session: {e}")
        except Exception as e:
            error_msg = f"Background task failed: {e}"
            logger.exception(error_msg)
            update_status(FileUploadStatus.FAILED, error_msg=error_msg)

    @staticmethod
    async def chat_endpoint(
        request: Request, user_query: str, chat_session_id: str, current_user, db, file_id: Optional[str] = None
    ):
        """Stream chat responses from the Tutor RAG Agent."""
        try:
            logger.info(f"Processing query: {user_query[:50]}...")

            # Store the user query in the database
            metadata = {
                "chat_session_id": chat_session_id,
                "user_id": str(current_user.id),
            }

            # Add file_id to metadata if provided
            if file_id:
                metadata["file_id"] = file_id
                logger.info(f"Adding file_id to message metadata: {file_id}")

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

            # ============= NEW: Fetch chat history for context =============
            chat_history = await ChatService.get_user_chat_history(
                db=db,
                user_id=str(current_user.id),
                limit=20,  # Last 20 messages from previous sessions
                exclude_current_session=chat_session_id
            )

            # Add chat history to user context
            if chat_history:
                user_context["chat_history"] = chat_history
                logger.info(f"📚 Including {len(chat_history)} historical messages for context")
            # ===========================================================

            # Call agent with timeout
            logger.info("Calling agent...")
            try:
                result = await asyncio.wait_for(
                    request.app.state.agent_server.handle_query(
                        query=user_query,
                        session_id=chat_session_id,
                        user_context=user_context,  # FIX: Pass user context with history
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
    async def get_user_chat_history(
        db: AsyncSession,
        user_id: str,
        limit: int = 20,
        exclude_current_session: Optional[str] = None
    ) -> list[dict]:
        """
        Fetch recent chat history for a user across all sessions.

        Args:
            db: Database session
            user_id: User ID
            limit: Maximum number of messages to fetch
            exclude_current_session: Session ID to exclude (current session)

        Returns:
            List of chat messages with role and content
        """
        try:
            from sqlalchemy import desc

            query = (
                select(ChatMessage)
                .join(ChatSession)
                .where(ChatSession.user_id == str(user_id))
                .order_by(desc(ChatMessage.created_at))
                .limit(limit)
            )

            if exclude_current_session:
                query = query.where(ChatSession.chat_session_id != exclude_current_session)

            result = await db.execute(query)
            messages = result.scalars().all()

            # Reverse to get chronological order
            history = [
                {
                    "role": msg.role,
                    "content": msg.content,
                    "timestamp": msg.created_at.isoformat() if msg.created_at else None
                }
                for msg in reversed(messages)
            ]

            logger.info(f"📚 Retrieved {len(history)} historical messages for user {user_id}")
            return history

        except Exception as e:
            logger.error(f"Failed to fetch chat history: {e}")
            return []

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
