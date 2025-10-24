"""
FastAPI router for lifelong learning progress tracking
Place this in: mcp_host/routers/progress.py
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from datetime import datetime

from mcp_host.database.db import get_db
from mcp_host.services.auths import get_current_user
from mcp_host.services.progress import ProgressService
from mcp_host.schemas.progress import (
    LearningSessionCreate,
    LearningSessionResponse,
    MilestoneCreate,
    MilestoneResponse,
    ProgressReportResponse,
    LearningTimelineResponse,
    WeeklyDigestResponse,
    KnowledgeRetentionAlert,
)
from mcp_host.models.users import User as UserModel
import logging

logger = logging.getLogger(__name__)

progress_router = APIRouter(prefix="/progress", tags=["progress"])


# ============= Learning Sessions =============


@progress_router.post("/sessions", response_model=LearningSessionResponse)
async def create_learning_session(
    session_data: LearningSessionCreate,
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new learning session record.

    This is typically called automatically after a chat session,
    but can also be used to manually log study time.
    """
    try:
        logger.info(f"Creating learning session for user {current_user.id}")
        session = await ProgressService.create_learning_session(
            db=db, user_id=current_user.id, session_data=session_data
        )
        return session
    except Exception as e:
        logger.error(f"Failed to create learning session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@progress_router.get("/sessions", response_model=List[LearningSessionResponse])
async def get_learning_sessions(
    subject: Optional[str] = None,
    days_back: int = Query(30, ge=1, le=365),
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get learning sessions for the current user.

    Filter by subject and time range.
    """
    try:
        sessions = await ProgressService.get_learning_sessions(
            db=db, user_id=current_user.id, subject=subject, days_back=days_back
        )
        return sessions
    except Exception as e:
        logger.error(f"Failed to get learning sessions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============= Milestones =============


@progress_router.post("/milestones", response_model=MilestoneResponse)
async def create_milestone(
    milestone_data: MilestoneCreate,
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new milestone achievement.

    This can be triggered automatically by the system (e.g., "5-day streak")
    or manually added by the user.
    """
    try:
        milestone = await ProgressService.create_milestone(
            db=db, user_id=current_user.id, milestone_data=milestone_data
        )
        logger.info(f"🎉 Milestone created: {milestone.title}")
        return milestone
    except Exception as e:
        logger.error(f"Failed to create milestone: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@progress_router.get("/milestones", response_model=List[MilestoneResponse])
async def get_milestones(
    subject: Optional[str] = None,
    limit: int = Query(50, ge=1, le=100),
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get all milestone achievements for the current user.

    Shows: "You mastered Calculus on March 15!", etc.
    """
    try:
        milestones = await ProgressService.get_user_milestones(
            db=db, user_id=current_user.id, subject=subject, limit=limit
        )
        return milestones
    except Exception as e:
        logger.error(f"Failed to get milestones: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============= Progress Reports =============


@progress_router.get("/report/{subject}", response_model=ProgressReportResponse)
async def get_progress_report(
    subject: str,
    days_back: int = Query(30, ge=7, le=365),
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Generate a comprehensive progress report for a specific subject.

    Includes:
    - Learning trajectory over time
    - Skill progression
    - Time investment breakdown
    - Strengths and areas for improvement
    - Recommended next topics
    - Topics needing review
    """
    try:
        logger.info(f"Generating progress report for {current_user.id} - {subject}")
        report = await ProgressService.generate_progress_report(
            db=db, user_id=current_user.id, subject=subject, days_back=days_back
        )
        return report
    except Exception as e:
        logger.error(f"Failed to generate progress report: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@progress_router.get("/timeline/{subject}", response_model=LearningTimelineResponse)
async def get_learning_timeline(
    subject: str,
    days_back: int = Query(90, ge=7, le=730),
    current_user: UserModel = Depends(get_current_user),
):
    """
    Get chronological timeline of all learning events.

    Perfect for visualizing: "You learned X on Jan 5, then Y on Jan 12..."
    Shows progression over weeks/months/years for lifelong learning.
    """
    try:
        logger.info(f"Generating timeline for {current_user.id} - {subject}")
        timeline = await ProgressService.get_learning_timeline(
            user_id=current_user.id, subject=subject, days_back=days_back
        )
        return timeline
    except Exception as e:
        logger.error(f"Failed to generate timeline: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============= Weekly Digest =============


@progress_router.get("/weekly-digest", response_model=WeeklyDigestResponse)
async def get_weekly_digest(
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Generate weekly learning summary.

    Returns:
    - Topics learned this week
    - Time spent studying
    - Milestones achieved
    - Learning streak
    - Topics needing review
    - Recommended goals for next week

    Perfect for weekly email notifications or app summary views.
    """
    try:
        logger.info(f"Generating weekly digest for {current_user.id}")
        digest = await ProgressService.generate_weekly_digest(
            db=db, user_id=current_user.id
        )
        return digest
    except Exception as e:
        logger.error(f"Failed to generate weekly digest: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============= Knowledge Retention =============


@progress_router.get("/retention-check", response_model=List[dict])
async def check_knowledge_retention(
    subject: Optional[str] = None,
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Check which topics need review based on time since last study.

    Returns topics not reviewed in 30+ days with risk assessment:
    - 30-45 days: Low risk
    - 45-60 days: Medium risk
    - 60+ days: High risk (knowledge decay likely)

    Supports lifelong learning by prompting periodic review.
    """
    try:
        alerts = await ProgressService._check_knowledge_retention(
            db=db, user_id=current_user.id, subject=subject
        )
        return alerts
    except Exception as e:
        logger.error(f"Failed to check retention: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============= Statistics =============


@progress_router.get("/stats/summary")
async def get_summary_statistics(
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get high-level summary statistics for dashboard display.

    Returns:
    - Total learning time (all time)
    - Total milestones achieved
    - Current learning streak
    - Topics studied count
    - Average difficulty level
    """
    try:
        # Get all sessions
        sessions = await ProgressService.get_learning_sessions(
            db=db,
            user_id=current_user.id,
            subject=None,
            days_back=365,  # Last year
        )

        # Get all milestones
        milestones = await ProgressService.get_user_milestones(
            db=db, user_id=current_user.id, subject=None, limit=100
        )

        # Calculate streak
        streak = await ProgressService._calculate_learning_streak(
            db=db, user_id=current_user.id
        )

        # Calculate stats
        total_time = sum(s.duration_minutes or 0 for s in sessions)
        unique_topics = len(set(s.topic for s in sessions))
        avg_difficulty = (
            sum(s.difficulty_level or 0 for s in sessions) / len(sessions)
            if sessions
            else 0
        )

        return {
            "total_study_time_minutes": total_time,
            "total_study_time_formatted": f"{total_time // 60}h {total_time % 60}m",
            "total_milestones": len(milestones),
            "current_streak_days": streak,
            "topics_studied": unique_topics,
            "average_difficulty_level": round(avg_difficulty, 2),
            "total_sessions": len(sessions),
        }

    except Exception as e:
        logger.error(f"Failed to get summary stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@progress_router.get("/stats/time-series")
async def get_time_series_data(
    subject: Optional[str] = None,
    days_back: int = Query(90, ge=7, le=365),
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get time-series data for charting progress over time.

    Returns daily/weekly aggregates of:
    - Study time
    - Difficulty level
    - Questions asked
    - Performance scores

    Perfect for visualizing learning trajectory graphs.
    """
    try:
        sessions = await ProgressService.get_learning_sessions(
            db=db, user_id=current_user.id, subject=subject, days_back=days_back
        )

        # Group by date
        daily_data = {}
        for session in sessions:
            date_key = session.session_date.date().isoformat()
            if date_key not in daily_data:
                daily_data[date_key] = {
                    "date": date_key,
                    "total_time": 0,
                    "questions": 0,
                    "avg_difficulty": 0,
                    "session_count": 0,
                }

            daily_data[date_key]["total_time"] += session.duration_minutes or 0
            daily_data[date_key]["questions"] += session.questions_asked
            daily_data[date_key]["session_count"] += 1

            if session.difficulty_level:
                daily_data[date_key]["avg_difficulty"] += session.difficulty_level

        # Calculate averages
        for data in daily_data.values():
            if data["session_count"] > 0:
                data["avg_difficulty"] /= data["session_count"]
                data["avg_difficulty"] = round(data["avg_difficulty"], 2)

        return {
            "time_series": sorted(daily_data.values(), key=lambda x: x["date"]),
            "total_days": len(daily_data),
            "date_range": {
                "start": min(daily_data.keys()) if daily_data else None,
                "end": max(daily_data.keys()) if daily_data else None,
            },
        }

    except Exception as e:
        logger.error(f"Failed to get time series data: {e}")
        raise HTTPException(status_code=500, detail=str(e))
