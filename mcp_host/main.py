"""
Updated mcp_host/main.py with lifelong learning features
Replace the existing main.py with this version
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from utils.azure_storage import AzureStorageManager
from mcp_host.mcp_agent.agents import TutoringRagAgent
import logging
from mcp_host.routers.chats import chat_router
from mcp_host.routers.auths import auth_router
from mcp_host.routers.progress import progress_router  # NEW
from mcp_host.routers.consent import consent_router  # NEW

# ============= LOGGING CONFIG =============
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)

logging.getLogger("uvicorn").setLevel(logging.INFO)
logging.getLogger("fastapi").setLevel(logging.INFO)
logging.getLogger("sqlalchemy").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)
# ============= END LOGGING CONFIG =============


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        "🚀 Initializing TutoringRagAgent server with lifelong learning features..."
    )

    try:
        app.state.storage_manager = AzureStorageManager()
        app.state.agent_server = TutoringRagAgent()
        await app.state.agent_server.initialized()
        logger.info("✅ TutoringRagAgent server initialized successfully")
        logger.info("📊 Lifelong learning progress tracking: ENABLED")
        logger.info("🔐 Consent management system: ENABLED")
    except Exception as e:
        logger.error(f"❌ Failed to initialize TutoringRagAgent server: {e}")
        raise

    yield

    logger.info("⏹️  Shutting down TutoringRagAgent server...")
    if hasattr(app.state, "agent_server"):
        logger.info("✅ TutoringRagAgent server shut down successfully")


# Create FastAPI app
app = FastAPI(
    title="TutorRagAgent API with Lifelong Learning",
    description="AI Tutoring System with Progress Tracking, Timeline, and Consent Management",
    version="2.0.0",  # Updated version
    lifespan=lifespan,
)


# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://ai-tutor-dypg.vercel.app",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============= INCLUDE ROUTERS =============
app.include_router(chat_router, prefix="/chats")
app.include_router(auth_router, prefix="/auth")
app.include_router(progress_router)  # NEW: Progress tracking
app.include_router(consent_router)  # NEW: Consent management
# ============= END ROUTERS =============


@app.get("/")
async def root(request: Request):
    logger.info("📍 Root endpoint called")
    base_url = str(request.base_url).rstrip("/")
    return {
        "message": "Welcome to TutorRagAgent with Lifelong Learning",
        "version": "2.0.0",
        "features": {
            "chat": "Real-time AI tutoring",
            "progress_tracking": "Learning sessions, milestones, and analytics",
            "timeline": "Chronological learning history",
            "consent_management": "GDPR-compliant privacy controls",
            "knowledge_retention": "Spaced repetition reminders",
        },
        "endpoints": {
            "docs": f"{base_url}/docs",
            "progress": f"{base_url}/progress",
            "consent": f"{base_url}/consent",
            "chats": f"{base_url}/chats",
            "auth": f"{base_url}/auth",
        },
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    logger.info("❤️  Health check called")
    return {
        "status": "healthy",
        "features": {
            "chat": "operational",
            "progress_tracking": "operational",
            "consent_management": "operational",
            "rag_system": "operational",
        },
    }


# Request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info(f"🌐 Request: {request.method} {request.url.path}")
    response = await call_next(request)
    logger.info(f"📤 Response: {response.status_code}")
    return response
