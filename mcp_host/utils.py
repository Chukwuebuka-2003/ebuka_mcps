from mcp_host.schemas.chats import UploadMetadata
from fastapi import Form
from typing import Dict, Any


def parse_upload_metadata(
    student_id: str = Form(...),
    subject: str = Form(...),
    topic: str = Form(...),
    difficulty_level: int = Form(...),
) -> UploadMetadata:
    return UploadMetadata(
        student_id=student_id,
        subject=subject,
        topic=topic,
        difficulty_level=difficulty_level,
    )


async def call_mcp_server_tool(
    sessions: dict, server_name: str, tool_name: str, tool_args: dict[str, Any]
) -> Any:
    session = sessions[server_name]["session"]
    return await session.call_tool(tool_name, tool_args)
