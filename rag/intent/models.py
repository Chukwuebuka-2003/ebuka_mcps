from dataclasses import dataclass, field
from enum import Enum
from typing import List
from pydantic import BaseModel, Field


class Goal(Enum):
    SOLVE_SPECIFIC_PROBLEM = "solve_specific_problem"
    UNDERSTAND_CONCEPT = "understand_concept"
    PREPARE_FOR_TEST = "prepare_for_test"
    EXPLORATION = "exploration"
    UNKNOWN = "unknown"


class AffectiveState(Enum):
    FRUSTRATED = "frustrated"
    CONFUSED = "confused"
    CURIOUS = "curious"
    CONFIDENT = "confident"
    NEUTRAL = "neutral"


class RiskFlag(Enum):
    PII_DETECTED = "pii_detected"
    SELF_HARM_CONCERN = "self_harm_concern"
    ACADEMIC_INTEGRITY_CONCERN = "academic_integrity_concern"
    INAPPROPRIATE_CONTENT = "inappropriate_content"


@dataclass
class ParsedIntent:
    original_text: str
    topic: str = "unknown"
    goal: Goal = Goal.UNKNOWN
    affective_state: AffectiveState = AffectiveState.NEUTRAL
    risk_flags: List[RiskFlag] = field(default_factory=list)


class IntentAnalysis(BaseModel):
    """Data model for the intent analysis"""

    topic: str = Field(..., description="The academic topic of the query")
    goal: Goal = Field(..., description="The student's primary learning goal")
    affective_state: AffectiveState = Field(
        ..., description="The student's emotional state"
    )


class IntentAnalysisResult(BaseModel):
    """Data model for the intent analysis"""

    topic: str = Field(..., description="The academic topic of the query")
    goal: Goal = Field(..., description="The student's primary learning goal")
    affective_state: AffectiveState = Field(
        ..., description="The student's emotional state"
    )
