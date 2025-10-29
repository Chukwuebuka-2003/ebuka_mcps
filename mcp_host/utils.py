from mcp_host.schemas.chats import UploadMetadata
from fastapi import Form
from typing import Dict, Any, Optional  # NEW: Import Optional


def parse_upload_metadata(
    student_id: str = Form(...),
    subject: str = Form(...),
    topic: str = Form(...),
    difficulty_level: int = Form(...),
    document_title: Optional[str] = Form(None),  # NEW: Document title parameter
) -> UploadMetadata:
    return UploadMetadata(
        student_id=student_id,
        subject=subject,
        topic=topic,
        difficulty_level=difficulty_level,
        document_title=document_title,  # NEW: Include document title
    )


async def call_mcp_server_tool(
    sessions: dict, server_name: str, tool_name: str, tool_args: dict[str, Any]
) -> Any:
    """
    Call an MCP server tool with preprocessing for compatibility.

    Automatically converts query arrays to strings for knowledge_base_retrieval
    to handle cases where AI agents send arrays instead of strings.
    """
    # Preprocess arguments for knowledge_base_retrieval tool
    if tool_name == "knowledge_base_retrieval" and "query" in tool_args:
        query = tool_args["query"]

        # Convert array to comma-separated string if needed
        if isinstance(query, list):
            tool_args["query"] = ", ".join(query)
            print(f"⚠️  Preprocessed query array to string: {tool_args['query'][:100]}...")

    session = sessions[server_name]["session"]
    return await session.call_tool(tool_name, tool_args)
