"""
Pydantic schemas for lifelong learning progress tracking
Place this in: mcp_host/schemas/progress.py
"""

from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from typing import List, Dict, Any, Optional
from uuid import UUID


# ============= Learning Session Schemas =============
class LearningSessionBase(BaseModel):
    subject: str = Field(..., description="Subject of the learning session")
    topic: str = Field(..., description="Specific topic studied")
    duration_minutes: Optional[int] = Field(
        None, description="Session duration in minutes"
    )
    performance_score: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="Performance score (0-1)"
    )
    questions_asked: int = Field(default=0, description="Number of questions asked")
    difficulty_level: Optional[int] = Field(
        None, ge=1, le=10, description="Difficulty level"
    )
    session_metadata: Optional[Dict[str, Any]] = Field(
        None, description="Additional metadata"
    )


class LearningSessionCreate(LearningSessionBase):
    session_date: datetime = Field(
        default_factory=datetime.utcnow, description="Session date/time"
    )


class LearningSessionResponse(LearningSessionBase):
    id: UUID
    user_id: UUID
    session_date: datetime
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ============= Milestone Schemas =============
class MilestoneBase(BaseModel):
    milestone_type: str = Field(
        ..., description="Type: 'topic_mastered', 'streak', 'difficulty_level_up', etc."
    )
    subject: str = Field(..., description="Subject area")
    topic: Optional[str] = Field(None, description="Specific topic")
    title: str = Field(..., description="Milestone title")
    description: Optional[str] = Field(None, description="Detailed description")
    milestone_metadata: Optional[Dict[str, Any]] = Field(
        None, description="Additional metadata"
    )


class MilestoneCreate(MilestoneBase):
    achieved_at: datetime = Field(default_factory=datetime.utcnow)


class MilestoneResponse(MilestoneBase):
    id: UUID
    user_id: UUID
    achieved_at: datetime
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ============= Progress Report Schemas =============
class TimelineEntry(BaseModel):
    """Individual learning event in timeline"""

    timestamp: datetime
    topic: str
    memory_type: str
    difficulty_level: int
    content_preview: str = Field(..., max_length=200)
    document_title: Optional[str] = None


class LearningTimelineResponse(BaseModel):
    """Complete learning timeline"""

    student_id: str
    subject: Optional[str]
    time_range: Dict[str, datetime]  # start, end
    total_events: int
    timeline: List[TimelineEntry]


class WeeklyActivity(BaseModel):
    """Activity summary for a week"""

    week_number: int
    start_date: datetime
    end_date: datetime
    total_interactions: int
    topics_covered: List[str]
    average_difficulty: float
    total_study_time_minutes: int


class ProgressReportResponse(BaseModel):
    """Comprehensive progress report"""

    student_id: str
    subject: str
    time_period_days: int
    generated_at: datetime

    # Summary metrics
    total_interactions: int
    skill_assessments: int
    error_patterns: int
    success_milestones: int

    # Learning trajectory
    topics_covered: List[str]
    difficulty_progression: List[int]

    # Time-based insights
    weekly_activity: List[WeeklyActivity]
    most_active_periods: List[str]
    total_study_time_minutes: int

    # Performance insights
    strengths: List[str]
    areas_for_improvement: List[str]
    recommended_next_topics: List[str]

    # Retention analysis
    topics_needing_review: List[Dict[str, Any]]  # Topics not reviewed recently


class KnowledgeRetentionAlert(BaseModel):
    """Alert for topics that need review"""

    topic: str
    subject: str
    last_studied: datetime
    days_since_review: int
    retention_risk: str = Field(..., description="'low', 'medium', or 'high'")
    recommendation: str


# ============= Consent Management Schemas =============
class ConsentStatusResponse(BaseModel):
    """Current consent status for a user"""

    consent_level: str  # 'full_profile', 'limited_anonymized', 'minimal_pseudonymous'
    granted_at: Optional[datetime]
    last_updated: Optional[datetime]
    data_retention_days: int
    sharing_preferences: Dict[str, bool]


class ConsentUpdateRequest(BaseModel):
    """Request to update consent level"""

    consent_level: str = Field(
        ...,
        description="'full_profile', 'limited_anonymized', or 'minimal_pseudonymous'",
    )
    data_retention_days: Optional[int] = Field(
        365, ge=30, le=3650, description="Days to retain data (30-3650)"
    )


class ConsentAuditLogResponse(BaseModel):
    """Consent change audit log entry"""

    id: UUID
    user_id: UUID
    action: str
    old_consent_level: Optional[str]
    new_consent_level: Optional[str]
    changed_at: datetime
    details: Optional[Dict[str, Any]]

    model_config = ConfigDict(from_attributes=True)


# ============= Weekly Digest Schema =============
class WeeklyDigestResponse(BaseModel):
    """Weekly learning summary"""

    week_start: datetime
    week_end: datetime

    summary: Dict[str, Any] = Field(..., description="Week summary statistics")
    achievements: List[str] = Field(..., description="Achievements this week")
    retention_checks: List[KnowledgeRetentionAlert] = Field(
        ..., description="Topics to review"
    )
    next_week_goals: List[str] = Field(..., description="Suggested goals for next week")
    learning_streak_days: int = Field(..., description="Current learning streak")


# ============= Comparison Schemas =============
class SubjectComparisonResponse(BaseModel):
    """Compare progress across multiple subjects"""

    student_id: str
    subjects: List[str]
    comparison_data: Dict[str, Dict[str, Any]]  # subject -> metrics
    generated_at: datetime
