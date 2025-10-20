import datetime
import json
import uuid
from contextlib import asynccontextmanager
from fastapi import (
    FastAPI,
    File,
    UploadFile,
    Form,
    HTTPException,
    Request,
    Depends,
    BackgroundTasks,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from omnicoreagent import OmniAgent, MemoryRouter, EventRouter, logger
from mcp_host.system_prompt import system_instruction
from mcp_host.schemas import ChatMessageRequest, UploadMetadata
from azure_storage import AzureStorageManager
from mcp_host.utils import parse_upload_metadata, call_mcp_server_tool
import logging


logging.basicConfig(level=logging.INFO)


MCP_TOOLS = [
    {
        "name": "turtor_rag",
        "transport_type": "streamable_http",
        "url": "http://0.0.0.0:9000/mcp",
        "headers": {
            "Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJteS1zZXJ2ZXItMDEiLCJleHAiOjE3NjEwNzg4MTAsImlhdCI6MTc2MDcxODgxMH0.Y6aWWx9-uy1S4LprE6mDwUzj-py8E1FnN7QHmWHHhpY"
        },
    }
]


class TutoringRagAgent:
    async def initialized(self):
        """Initialize the TutoringRagAgent server."""

        # Create memory and event routers
        self.memory_router = MemoryRouter(memory_store_type="in_memory")
        self.event_router = EventRouter(event_store_type="in_memory")

        # Create the OmniAgent
        self.agent = OmniAgent(
            name="TutoringRagAgent",
            system_instruction=system_instruction,
            model_config={
                "provider": "openai",
                "model": "gpt-4.1",
                "temperature": 0.3,
                "max_context_length": 5000,
                "top_p": 0.7,
            },
            mcp_tools=MCP_TOOLS,
            agent_config={
                "agent_name": "TutoringRagAgent",
                "max_steps": 15,
                "tool_call_timeout": 60,
                "request_limit": 0,  # 0 = unlimited
                "total_tokens_limit": 0,  # or 0 for unlimited
                # --- Memory Retrieval Config ---
                "memory_config": {"mode": "sliding_window", "value": 100},
                "memory_results_limit": 5,
                "memory_similarity_threshold": 0.5,
                # --- Tool Retrieval Config ---
                "enable_tools_knowledge_base": False,
                "tools_results_limit": 10,
                "tools_similarity_threshold": 0.1,
                "memory_tool_backend": "local",
            },
            memory_router=self.memory_router,
            event_router=self.event_router,
            debug=True,
        )
        await self.agent.connect_mcp_servers()
        self.mcp_client = self.agent.mcp_client

    async def handle_query(self, query: str, session_id: str = None) -> dict:
        """Handle a user query and return the agent's response.

        Args:
            query: User's query/message
            session_id: Optional session ID for conversation continuity

        Returns:
            Dict with response and session_id
        """
        try:
            # Run the agent
            result = await self.agent.run(query, session_id)
            return result

        except Exception as e:
            logger.error(f"Failed to process query: {e}")
            return {
                "response": f"I apologize, but I encountered an error: {str(e)}",
                "session_id": session_id or "error_session",
            }

    async def get_session_history(self, session_id: str) -> list[dict]:
        """Get conversation history for a session."""
        try:
            return await self.agent.get_session_history(session_id)
        except Exception as e:
            logger.error(f"Failed to get session history: {e}")
            return []

    async def clear_session_memory(self, session_id: str) -> bool:
        """Clear memory for a specific session."""
        try:
            await self.agent.clear_session_history(session_id)
            logger.info(f"Cleared memory for session: {session_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to clear session memory: {e}")
            return False

    def get_agent_info(self) -> dict:
        """Get information about the agent configuration."""
        return {
            "agent_name": self.agent.name,
            "memory_store_type": "in_memory",
            "memory_store_info": self.memory_store.get_memory_store_info(),
            "event_store_type": self.agent.get_event_store_type(),
            "debug_mode": self.agent.debug,
        }


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing TutoringRagAgent server...")

    try:
        app.state.storage_manager = AzureStorageManager()
        app.state.agent_server = TutoringRagAgent()
        await app.state.agent_server.initialized()
        logger.info("TutoringRagAgent server initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize TutoringRagAgent server: {e}")
        raise

    yield  # The application runs here

    # This code executes when the application is shutting down
    logger.info("Shutting down TutoringRagAgent server...")
    if hasattr(app.state, "agent_server"):
        # Cleanup if needed
        logger.info("TutoringRagAgent server shut down successfully")


# Initialize FastAPI with the lifespan
app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/upload-student-file")
async def upload_student_file(
    request: Request,
    background_tasks: BackgroundTasks,
    meta: UploadMetadata = Depends(parse_upload_metadata),
    file: UploadFile = File(...),
):
    """
    Upload a student file (PDF/DOCX) with metadata.
    Returns immediately; processing happens in the background.
    """
    try:
        file_content = await file.read()
        if not file_content:
            raise HTTPException(status_code=400, detail="Uploaded file is empty")

        filename = file.filename or "unnamed_file"

        # Return success immediately
        response = {
            "status": "success",
            "message": "Your file has been received and is being processed. You'll be able to interact with its content shortly!",
        }

        # Schedule background work
        background_tasks.add_task(
            _process_uploaded_file,
            request.app.state.storage_manager,
            request.app.state.agent_server.mcp_client,
            file_content,
            filename,
            file.content_type or "application/octet-stream",
            meta,
        )

        return response

    except HTTPException:
        raise
    except Exception as e:
        logging.exception(f"Unexpected error during file upload: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


def _process_uploaded_file(
    storage_manager,
    mcp_client,
    file_content: bytes,
    filename: str,
    content_type: str,
    meta: UploadMetadata,
):
    try:
        # Upload to Azure
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

        if upload_result["status"] != "success":
            logging.error(f"Background upload failed: {upload_result.get('message')}")
            return

        # Trigger MCP tool call processing
        file_id = upload_result["blob_name"]
        mcp_sessions = getattr(mcp_client, "sessions", None)
        if not mcp_sessions:
            logging.error("MCP sessions not available")
            return

        import asyncio

        asyncio.run(
            call_mcp_server_tool(
                sessions=mcp_sessions,
                server_name="TutoringRAGSystemMCPServer",
                tool_name="upload_student_file",
                tool_args={
                    "user_id": meta.student_id,
                    "filename": filename,
                    "file_id": file_id,
                    "subject": meta.subject,
                    "topic": meta.topic,
                    "difficulty_level": meta.difficulty_level,
                },
            )
        )

        logging.info(f"Background processing completed for {file_id}")

    except Exception as e:
        logging.exception(f"Background task failed: {e}")


@app.get("/events/{session_id}")
async def stream_events(request: Request, session_id: str):
    """Stream events for a specific session."""

    async def event_generator():
        try:
            async for event in request.app.state.agent_server.agent.stream_events(
                session_id
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


async def chat_endpoint(request: Request, user_input: str, session_id: str):
    """Handle chat endpoint with streaming response."""
    try:
        print("chat_endpoint MCPClient:", request.app.state.agent_server.mcp_client)
        print(
            "chat_endpoint MCP sessions:",
            getattr(request.app.state.agent_server.mcp_client, "sessions", None),
        )

        result = await request.app.state.agent_server.handle_query(
            query=user_input, session_id=session_id
        )

        response = {
            "role": "assistant",
            "content": result["response"],
            "session_id": result["session_id"],
            "agent_name": result["agent_name"],
        }
        yield (json.dumps(response).encode("utf-8") + b"\n")
    except Exception as e:
        logger.error(f"Error processing query: {e}")
        response = {
            "role": "assistant",
            "content": f"Error processing query: {e}",
            "session_id": session_id,
        }
        yield (json.dumps(response).encode("utf-8") + b"\n")


@app.post("/chats/tutor-rag-agent")
async def chat(request: Request, chat_message_request: ChatMessageRequest):
    logger.info(f"chat request message: {chat_message_request}")
    session_id = chat_message_request.session_id
    if not session_id:
        session_id = str(uuid.uuid4())
    return StreamingResponse(
        chat_endpoint(
            request=request,
            user_input=chat_message_request.messages[-1].content,
            session_id=session_id,
        ),
        media_type="text/plain",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@app.get("/session/{session_id}/history")
async def get_session_history(request: Request, session_id: str):
    """Get conversation history for a specific session."""
    try:
        history = await request.app.state.agent_server.get_session_history(session_id)
        return {
            "status": "success",
            "session_id": session_id,
            "history": history,
            "message_count": len(history),
        }
    except Exception as e:
        logger.error(f"Error getting session history: {e}")
        return {"status": "error", "message": str(e)}


@app.delete("/session/{session_id}/memory")
async def clear_session_memory(request: Request, session_id: str):
    """Clear memory for a specific session."""
    try:
        success = await request.app.state.agent_server.clear_session_memory(session_id)
        return {
            "status": "success" if success else "error",
            "session_id": session_id,
            "message": "Memory cleared successfully"
            if success
            else "Failed to clear memory",
        }
    except Exception as e:
        logger.error(f"Error clearing session memory: {e}")
        return {"status": "error", "message": str(e)}


@app.get("/agent/info")
async def get_agent_info(request: Request):
    """Get information about the agent configuration."""
    try:
        info = request.app.state.agent_server.get_agent_info()
        return {"status": "success", "agent_info": info}
    except Exception as e:
        logger.error(f"Error getting agent info: {e}")
        return {"status": "error", "message": str(e)}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
