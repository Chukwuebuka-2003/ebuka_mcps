from typing import Annotated, Optional
from pydantic import Field
from fastmcp.tools.tool import ToolResult
from fastmcp.exceptions import ToolError
import json
from utils.rag_interface import knowledge_base_retrieval_interface
from fastmcp import FastMCP, Context
from fastapi.responses import JSONResponse

from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp.server.dependencies import get_http_headers
from utils.jwt_util import verify_server_token

from utils.azure_storage import AzureStorageManager
from utils.file_processor import FileProcessor
from rag.system import TutoringRAGSystem


class AuthHeaderMiddleware(Middleware):
    async def on_call_tool(self, context: MiddlewareContext, call_next):
        headers = get_http_headers()
        auth = headers.get("authorization")

        is_verified = False
        payload = None

        if auth and auth.startswith("Bearer "):
            token = auth.split("Bearer ")[1].strip()
            try:
                payload = verify_server_token(token)
                is_verified = True
            except Exception:
                is_verified = False

        context.fastmcp_context.set_state("auth_verified", is_verified)
        context.fastmcp_context.set_state("auth_payload", payload)

        return await call_next(context)


mcp = FastMCP(
    name="TutoringRAGSystemMCPServer",
    instructions="""
This TutoringRAGSystem MCP server manages user-scoped knowledge bases for personalized tutoring and learning.

It exposes tools for:
1. Knowledge retrieval from stored learning interactions with citations
2. File uploads with automatic text extraction and storage
3. File management and listing

=== Tool Descriptions ===

- knowledge_base_retrieval:
  Retrieve stored knowledge for a specific user with contextual search and document citations.

- upload_student_file:
  Upload PDF or DOCX files, automatically extract text, and store in the RAG system.
  Supports both file storage in Azure Blob Storage and content indexing for retrieval.
  Accepts optional document_title parameter for better citation tracking.

All tools require valid JWT authentication via Bearer token.
""",
)

mcp.add_middleware(AuthHeaderMiddleware())

# Initialize services
azure_storage = AzureStorageManager()
rag_system = TutoringRAGSystem()
file_processor = FileProcessor(rag_system)


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request):
    """Health check endpoint."""
    return JSONResponse(
        {
            "status": "healthy",
            "service": "rag_mcp_server",
            "tools_available": ["knowledge_base_retrieval", "upload_student_file"],
        }
    )


@mcp.tool(
    name="knowledge_base_retrieval",
    description="""
    Retrieve personalized knowledge for a specific user from their stored content.

    This tool performs a contextual search across a user's private knowledge base
    using semantic and keyword-based retrieval. Returns responses with document citations.

    IMPORTANT: The 'query' parameter must be a single string, NOT a list or array.
    Use comma or space separated keywords in one string.
    Example: "calculus derivatives, power rule, differentiation"
    NOT: ["calculus", "derivatives", "power rule"]
    """,
)
def knowledge_base_retrieval(
    ctx: Context,
    user_id: Annotated[
        str, Field(description="Unique ID of the user whose content is being searched.")
    ],
    query: Annotated[
        str,  # MUST be a string - arrays/lists will be rejected
        Field(
            description="A SINGLE STRING containing natural language search query or comma/space-separated keywords. CRITICAL: This MUST be a string, NOT an array or list. Example: 'photosynthesis chlorophyll light reaction' NOT ['photosynthesis', 'chlorophyll']. Use comma or space separated keywords in a single string.",
            json_schema_extra={
                "type": "string",
                "examples": [
                    "quadratic equation, quadratic formula, solving polynomials",
                    "photosynthesis process light reaction chlorophyll",
                    "World War II causes treaty of versailles"
                ]
            }
        ),
    ],
    subject: Annotated[
        str, Field(description="Subject of the query (e.g., 'Mathematics', 'History').")
    ],
    topic: Annotated[
        str,
        Field(
            description="Topic within the subject (e.g., 'Algebra', 'World War II')."
        ),
    ],
    top_k: Annotated[
        int, Field(description="Number of results to return. Default=3")
    ] = 3,
) -> ToolResult:
    """
    MCP tool wrapper around the RAG retrieval system for user-specific context.
    """
    import traceback

    try:
        print(f"=" * 80)
        print(f"🔍 knowledge_base_retrieval called")
        print(f"  user_id: {user_id}")
        print(f"  query: {query} (type: {type(query).__name__})")
        print(f"  subject: {subject}")
        print(f"  topic: {topic}")
        print(f"  top_k: {top_k}")
        print(f"=" * 80)

        # Validate query is a string
        if not isinstance(query, str):
            raise ValueError(f"Query must be a string, not {type(query).__name__}. Use comma or space separated keywords in a single string.")

        # Check authentication
        if not ctx.get_state("auth_verified"):
            return ToolResult(
                content=json.dumps(
                    {
                        "status": "error",
                        "message": "Unauthorized: token verification failed.",
                    }
                )
            )

        print("Authentication verified")
        print("Calling knowledge_base_retrieval_interface...")

        # Call the RAG interface
        result = knowledge_base_retrieval_interface(
            student_id=user_id,
            current_question=query,
            subject=subject,
            topic=topic,
            context_limit=top_k,
        )

        print(f"RAG interface returned result")
        print(f"   Result type: {type(result)}")
        print(f"   Result preview: {str(result)[:200]}...")

        # Result should be a string
        if not isinstance(result, str):
            raise ValueError(f"Expected string result, got {type(result)}")

        return ToolResult(
            content=json.dumps(
                {
                    "status": "success",
                    "user_id": user_id,
                    "query": query,
                    "response": result,
                }
            )
        )

    except Exception as e:
        error_details = traceback.format_exc()
        print(f"❌ ERROR in knowledge_base_retrieval:")
        print(error_details)
        raise ToolError(
            f"Failed to retrieve knowledge: {str(e)}\n\nDetails:\n{error_details}"
        )


@mcp.tool(
    name="upload_student_file",
    description="""
    Upload a PDF or DOCX file, extract text content, and store in both Azure Blob Storage
    and the RAG system for future retrieval. Accepts optional document_title for citations.
    """,
)
def process_existing_file(
    ctx: Context,
    user_id: Annotated[str, Field(description="Unique ID of the student.")],
    filename: Annotated[
        str,
        Field(
            description="Original filename with extension (e.g., 'notes.pdf', 'chapter1.docx')"
        ),
    ],
    file_id: Annotated[
        str, Field(description="The blob name (file_id) returned from upload endpoint")
    ],
    subject: Annotated[
        str, Field(description="Subject category (e.g., 'Mathematics', 'History')")
    ],
    topic: Annotated[
        Optional[str], Field(description="Optional specific topic within the subject")
    ] = None,
    difficulty_level: Annotated[
        int, Field(description="Difficulty level 1-10 (default: 5)")
    ] = 5,
    description: Annotated[
        Optional[str], Field(description="Optional description of the file content")
    ] = None,
    document_title: Annotated[
        Optional[str],
        Field(
            description="Optional custom document title for citations (defaults to filename)"
        ),
    ] = None,  
) -> ToolResult:
    """
    Download the file from Azure and index it into the RAG system with citation metadata.
    """
    try:
        if not ctx.get_state("auth_verified"):
            return ToolResult(
                content=json.dumps(
                    {
                        "status": "error",
                        "message": "Unauthorized: token verification failed.",
                    }
                )
            )

        file_extension = filename.lower().split(".")[-1]
        if file_extension not in ["pdf", "docx", "doc"]:
            raise ToolError(
                f"Unsupported file type: {file_extension}. Only PDF and DOCX files are supported."
            )

        file_content = azure_storage.download_file(file_id)
        if file_content is None:
            raise ToolError(f"File not found in storage: {file_id}")

        metadata = {}
        if description:
            metadata["description"] = description

        processing_result = file_processor.process_and_store_file(
            file_content=file_content,
            filename=filename,
            student_id=user_id,
            subject=subject,
            topic=topic,
            difficulty_level=difficulty_level,
            document_title=document_title,  
            additional_metadata={
                "blob_name": file_id,
                "description": description,
                **metadata,
            },
        )

        if processing_result["status"] != "success":
            return ToolResult(
                content=json.dumps(
                    {
                        "status": "error",
                        "message": "Text extraction and indexing failed",
                        "error": processing_result.get("message"),
                    }
                )
            )

        return ToolResult(
            content=json.dumps(
                {
                    "status": "success",
                    "message": f"File '{filename}' processed and indexed successfully",
                    "file_id": file_id,
                    "document_title": processing_result.get("document_title", filename),
                    "detected_subject": processing_result.get("detected_subject", subject),
                    "processing_info": {
                        "total_characters": processing_result["total_characters"],
                        "chunks_stored": processing_result["chunks_stored"],
                        "extraction_metadata": processing_result.get("metadata", {}),
                    },
                }
            )
        )

    except Exception as e:
        raise ToolError(f"Failed to process file: {str(e)}")


if __name__ == "__main__":
    import os
    port = int(os.getenv("PORT", 9000))
    mcp.run(
        transport="http",
        host="0.0.0.0",
        port=port,
        log_level="DEBUG",
    )
