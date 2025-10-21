from typing import Annotated, Optional
from pydantic import Field
from fastmcp.tools.tool import ToolResult
from fastmcp.exceptions import ToolError
import json
from utils.rag_interface import knowledge_base_retrieval_interface
from fastmcp import FastMCP, Context

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
1. Knowledge retrieval from stored learning interactions
2. File uploads with automatic text extraction and storage
3. File management and listing

=== Tool Descriptions ===

- knowledge_base_retrieval:
  Retrieve stored knowledge for a specific user with contextual search.

- upload_student_file:
  Upload PDF or DOCX files, automatically extract text, and store in the RAG system.
  Supports both file storage in Azure Blob Storage and content indexing for retrieval.

- list_student_files:
  List all files uploaded by a student, optionally filtered by subject.

- get_file_download_url:
  Generate temporary secure download URLs for uploaded files.

- preview_file_text:
  Extract and preview text from a file without storing it permanently.

All tools require valid JWT authentication via Bearer token.
""",
)

mcp.add_middleware(AuthHeaderMiddleware())

# Initialize services
azure_storage = AzureStorageManager()
rag_system = TutoringRAGSystem()
file_processor = FileProcessor(rag_system)


@mcp.tool(
    name="knowledge_base_retrieval",
    description="""
    Retrieve personalized knowledge for a specific user from their stored content.

    This tool performs a contextual search across a user's private knowledge base
    using semantic and keyword-based retrieval. It is primarily used by agents or UIs
    to fetch user-specific notes, explanations, or stored learning materials relevant
    to a given query.

    ### Behavior
    - Requires a valid authorization token (verified by middleware) before execution.
    - Filters results by the provided `user_id`, ensuring access to only that user's content.
    - Searches within a specific `subject` and `topic` context to improve relevance.
    - Returns up to `top_k` of the most relevant results along with metadata and content.

    ### Typical Use Cases
    - When generating answers or explanations using the user's previously stored notes.
    - When reviewing, revising, or summarizing knowledge in a user-specific context.
    - When building an adaptive learning or tutoring agent that personalizes responses.

    ### Parameters
    - **user_id**: Unique identifier of the user whose stored knowledge is being retrieved.
    - **query**: The natural-language question or keywords to search for.
    - **subject**: The subject domain to restrict search scope (e.g., "Mathematics").
    - **topic**: A more specific area within the subject (e.g., "Algebra").
    - **top_k**: Maximum number of results to return (default: 3).

    ### Notes
    - Returns an error if the request is unauthorized (token verification fails).
    - Use this tool to power context-aware reasoning or personalized responses.
    """,
)
def knowledge_base_retrieval(
    ctx: Context,
    user_id: Annotated[
        str, Field(description="Unique ID of the user whose content is being searched.")
    ],
    query: Annotated[
        str,
        Field(
            description="Natural language search query or keywords to match against the user's stored content."
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
) -> ToolResult | dict:
    """
    MCP tool wrapper around the RAG retrieval system for user-specific context.
    """
    try:
        if not ctx.get_state("auth_verified"):
            return {
                "status": "error",
                "message": "Unauthorized: token verification failed.",
            }

        result = knowledge_base_retrieval_interface(
            student_id=user_id,
            current_question=query,
            subject=subject,
            topic=topic,
            context_limit=top_k,
        )

        return ToolResult(
            content=json.dumps(
                {
                    "status": "success",
                    "user_id": user_id,
                    "query": query,
                    "results": result,
                }
            )
        )

    except Exception as e:
        raise ToolError(f"Failed to retrieve knowledge: {str(e)}")


@mcp.tool(
    name="upload_student_file",
    description="""
    Upload a PDF or DOCX file, extract text content, and store in both Azure Blob Storage
    and the RAG system for future retrieval.

    **Supported file formats: PDF, DOCX**

    This tool performs multiple operations:
    1. Uploads the file to Azure Blob Storage for archival
    2. Extracts all text content from the file (using PyMuPDF for PDFs, python-docx for DOCX)
    3. Chunks the text into manageable segments with overlap
    4. Stores each chunk in the RAG system for semantic search
    5. Returns metadata about the upload and processing

    **Extracted content includes:**
    - For PDFs: All text from all pages, page numbers, image detection
    - For DOCX: All paragraphs and tables with formatting preserved

    **Use cases:**
    - Student uploads study notes or handouts
    - Student uploads assignments or homework for context
    - Student uploads textbook chapters or reference materials
    - Storing learning materials for later context-aware tutoring

    **The extracted text becomes searchable** via the knowledge_base_retrieval tool.
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
) -> ToolResult:
    """
    download the file from Azure and index it into the RAG system.

    """
    try:
        # Verify authentication
        if not ctx.get_state("auth_verified"):
            return ToolResult(
                content=json.dumps(
                    {
                        "status": "error",
                        "message": "Unauthorized: token verification failed.",
                    }
                )
            )

        # Validate file type
        file_extension = filename.lower().split(".")[-1]
        if file_extension not in ["pdf", "docx", "doc"]:
            raise ToolError(
                f"Unsupported file type: {file_extension}. Only PDF and DOCX files are supported."
            )

        file_content = azure_storage.download_file(file_id)
        if file_content is None:
            raise ToolError(f"File not found in storage: {file_id}")

        # Prepare metadata
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


# @mcp.tool(
#     name="preview_file_text",
#     description="""
#     Extract and preview text from a PDF or DOCX file without storing it.

#     Use this tool to:
#     - Show users what text will be extracted before storing
#     - Verify file content and extraction quality
#     - Check if the file contains meaningful text

#     Returns a preview (first 500 characters by default) of extracted text
#     along with metadata about the file structure.
#     """,
# )
# def preview_file_text(
#     ctx: Context,
#     filename: Annotated[
#         str, Field(description="Filename with extension (e.g., 'notes.pdf')")
#     ],
#     file_content_base64: Annotated[
#         str, Field(description="Base64-encoded file content")
#     ],
#     max_chars: Annotated[
#         int, Field(description="Maximum characters to return in preview (default: 500)")
#     ] = 500,
# ) -> ToolResult:
#     """
#     Preview extracted text from a file without storing it.
#     """
#     try:
#         # Verify authentication
#         if not ctx.get_state("auth_verified"):
#             return ToolResult(
#                 content=json.dumps(
#                     {
#                         "status": "error",
#                         "message": "Unauthorized: token verification failed.",
#                     }
#                 )
#             )

#         # Decode base64 content
#         try:
#             file_content = base64.b64decode(file_content_base64)
#         except Exception as e:
#             raise ToolError(f"Invalid base64 content: {str(e)}")

#         # Extract preview
#         preview_result = file_processor.extract_text_preview(
#             file_content=file_content,
#             filename=filename,
#             max_chars=max_chars,
#         )

#         if preview_result["status"] != "success":
#             raise ToolError(preview_result.get("message", "Preview extraction failed"))

#         return ToolResult(
#             content=json.dumps(
#                 {
#                     "status": "success",
#                     "filename": filename,
#                     "preview": preview_result["preview"],
#                     "total_characters": preview_result["total_characters"],
#                     "metadata": preview_result["metadata"],
#                 }
#             )
#         )

#     except Exception as e:
#         raise ToolError(f"Failed to preview file: {str(e)}")


# @mcp.tool(
#     name="list_student_files",
#     description="""
#     List all files previously uploaded by a specific student.

#     Use this to:
#     - Show a student their uploaded materials
#     - Find specific files for reference during tutoring
#     - Filter files by subject area

#     Returns a list of files with metadata including filenames,
#     upload timestamps, sizes, and download URLs.
#     """,
# )
# def list_student_files(
#     ctx: Context,
#     user_id: Annotated[
#         str, Field(description="Unique ID of the student whose files to list.")
#     ],
#     subject: Annotated[
#         Optional[str], Field(description="Optional subject filter")
#     ] = None,
# ) -> ToolResult:
#     """
#     List all files for a student, optionally filtered by subject.
#     """
#     try:
#         # Verify authentication
#         if not ctx.get_state("auth_verified"):
#             return ToolResult(
#                 content=json.dumps(
#                     {
#                         "status": "error",
#                         "message": "Unauthorized: token verification failed.",
#                     }
#                 )
#             )

#         files = azure_storage.list_student_files(student_id=user_id, subject=subject)

#         return ToolResult(
#             content=json.dumps(
#                 {
#                     "status": "success",
#                     "user_id": user_id,
#                     "subject_filter": subject,
#                     "file_count": len(files),
#                     "files": files,
#                 }
#             )
#         )

#     except Exception as e:
#         raise ToolError(f"Failed to list files: {str(e)}")


# @mcp.tool(
#     name="get_file_download_url",
#     description="""
#     Generate a temporary download URL for a student's file.

#     Returns a secure, time-limited URL (valid for 24 hours by default)
#     that can be used to download the file without requiring authentication.

#     Useful for:
#     - Providing students access to their uploaded materials
#     - Sharing files with tutors or reviewers
#     - Downloading files for processing or analysis
#     """,
# )
# def get_file_download_url(
#     ctx: Context,
#     blob_name: Annotated[str, Field(description="Full blob name/path of the file")],
#     expiry_hours: Annotated[
#         int, Field(description="Hours until the URL expires (default: 24)")
#     ] = 24,
# ) -> ToolResult:
#     """
#     Generate a temporary SAS URL for downloading a file.
#     """
#     try:
#         # Verify authentication
#         if not ctx.get_state("auth_verified"):
#             return ToolResult(
#                 content=json.dumps(
#                     {
#                         "status": "error",
#                         "message": "Unauthorized: token verification failed.",
#                     }
#                 )
#             )

#         download_url = azure_storage.generate_download_url(
#             blob_name=blob_name, expiry_hours=expiry_hours
#         )

#         if download_url:
#             return ToolResult(
#                 content=json.dumps(
#                     {
#                         "status": "success",
#                         "blob_name": blob_name,
#                         "download_url": download_url,
#                         "expires_in_hours": expiry_hours,
#                     }
#                 )
#             )
#         else:
#             raise ToolError("Failed to generate download URL")

#     except Exception as e:
#         raise ToolError(f"Failed to generate download URL: {str(e)}")


if __name__ == "__main__":
    mcp.run(
        transport="http",
        host="0.0.0.0",
        port=9000,
        log_level="DEBUG",
    )
