from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from utils.azure_storage import AzureStorageManager
from mcp_host.mcp_agent.agents import TutoringRagAgent
import logging
from mcp_host.routers.chats import chat_router


logger = logging.getLogger(__name__)


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

    yield

    logger.info("Shutting down TutoringRagAgent server...")
    if hasattr(app.state, "agent_server"):
        logger.info("TutoringRagAgent server shut down successfully")


# Create FastAPI app
app = FastAPI(
    title="TutorRagAgent API",
    description="TutorRagAgent",
    version="1.0.0",
    lifespan=lifespan,
)


# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure this properly for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Include routers
app.include_router(chat_router, prefix="/chats")


@app.get("/")
async def root(request: Request):
    base_url = str(request.base_url).rstrip("/")
    return {
        "message": "Welcome to TutorRagAgent",
        "version": "1.0.0",
        "docs": f"{base_url}/docs",
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}
