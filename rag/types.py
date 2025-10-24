from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional


class MemoryType(Enum):
    LEARNING_INTERACTION = "learning_interaction"
    SKILL_ASSESSMENT = "skill_assessment"
    CONTENT_MASTERY = "content_mastery"
    LEARNING_PREFERENCE = "learning_preference"
    ERROR_PATTERN = "error_pattern"
    SUCCESS_MILESTONE = "success_milestone"


@dataclass
class LearningContext:
    student_id: str
    subject: str
    topic: str
    difficulty_level: int
    learning_style: str
    timestamp: datetime
    content: str
    memory_type: MemoryType
    metadata: Optional[Dict[str, Any]] = None
    document_title: Optional[str] = None
