"""
Automatic Learning Session Tracking
Place this in: mcp_host/services/session_tracker.py

This service automatically creates learning session records
when students interact with the tutoring system.
"""
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
import logging

from mcp_host.models.progress import LearningSession, Milestone
from mcp_host.schemas.progress import LearningSessionCreate, MilestoneCreate
from mcp_host.services.progress import ProgressService

logger = logging.getLogger(__name__)


class SessionTracker:
    """Automatically track learning sessions and trigger milestones"""
    
    @staticmethod
    async def track_chat_session(
        db: AsyncSession,
        user_id: UUID,
        subject: str,
        topic: str,
        difficulty_level: int,
        duration_minutes: Optional[int] = None,
        questions_asked: int = 1
    ):
        """
        Automatically create a learning session record after a chat interaction.
        
        This should be called from the chat endpoint after each successful interaction.
        """
        try:
            session_data = LearningSessionCreate(
                subject=subject,
                topic=topic,
                duration_minutes=duration_minutes,
                session_date=datetime.now(timezone.utc),
                questions_asked=questions_asked,
                difficulty_level=difficulty_level,
                session_metadata={
                    "tracked_automatically": True,
                    "source": "chat"
                }
            )
            
            session = await ProgressService.create_learning_session(
                db=db,
                user_id=user_id,
                session_data=session_data
            )
            
            logger.info(f"📊 Tracked learning session: {subject}/{topic} for user {user_id}")
            
            # Check if this triggers any milestones
            await SessionTracker._check_milestone_triggers(db, user_id, subject, topic)
            
            return session
            
        except Exception as e:
            logger.error(f"Failed to track session: {e}")
            # Don't raise - session tracking shouldn't break chat
    
    @staticmethod
    async def _check_milestone_triggers(
        db: AsyncSession,
        user_id: UUID,
        subject: str,
        topic: str
    ):
        """
        Check if any milestones should be triggered based on recent activity.
        
        Milestone types:
        - learning_streak: X consecutive days
        - topic_sessions: Y sessions on same topic
        - subject_mastery: Z topics covered in subject
        - difficulty_progression: Reached difficulty level X
        """
        try:
            from sqlalchemy import select, func
            from datetime import timedelta
            
            # Check learning streak
            streak = await ProgressService._calculate_learning_streak(db, user_id)
            
            if streak in [3, 5, 7, 14, 30, 60, 100]:  # Milestone thresholds
                # Check if milestone already exists
                existing = await db.execute(
                    select(Milestone).where(
                        Milestone.user_id == user_id,
                        Milestone.milestone_type == 'learning_streak',
                        Milestone.milestone_metadata['streak_days'].astext == str(streak)
                    )
                )
                
                if not existing.scalar_one_or_none():
                    milestone_data = MilestoneCreate(
                        milestone_type='learning_streak',
                        subject='General',
                        title=f"🔥 {streak}-Day Learning Streak!",
                        description=f"You've studied for {streak} consecutive days. Amazing consistency!",
                        milestone_metadata={
                            "streak_days": streak,
                            "achievement_date": datetime.now(timezone.utc).isoformat()
                        }
                    )
                    
                    await ProgressService.create_milestone(db, user_id, milestone_data)
                    logger.info(f"🎉 Milestone triggered: {streak}-day streak for user {user_id}")
            
            # Check topic mastery (10+ sessions on same topic)
            topic_session_count = await db.execute(
                select(func.count(LearningSession.id)).where(
                    LearningSession.user_id == user_id,
                    LearningSession.topic == topic
                )
            )
            count = topic_session_count.scalar()
            
            if count == 10:  # First time reaching 10 sessions
                milestone_data = MilestoneCreate(
                    milestone_type='topic_mastery',
                    subject=subject,
                    topic=topic,
                    title=f"📚 {topic} Mastery",
                    description=f"Completed 10 learning sessions on {topic}!",
                    milestone_metadata={
                        "sessions_count": count,
                        "topic": topic
                    }
                )
                
                await ProgressService.create_milestone(db, user_id, milestone_data)
                logger.info(f"🎉 Milestone triggered: Topic mastery for {topic}")
            
        except Exception as e:
            logger.error(f"Failed to check milestone triggers: {e}")
    
    @staticmethod
    async def track_file_upload(
        db: AsyncSession,
        user_id: UUID,
        subject: str,
        topic: str,
        filename: str
    ):
        """
        Track when a student uploads study materials.
        Creates a session and potentially triggers milestones.
        """
        try:
            session_data = LearningSessionCreate(
                subject=subject,
                topic=topic,
                session_date=datetime.now(timezone.utc),
                questions_asked=0,
                session_metadata={
                    "tracked_automatically": True,
                    "source": "file_upload",
                    "filename": filename
                }
            )
            
            await ProgressService.create_learning_session(
                db=db,
                user_id=user_id,
                session_data=session_data
            )
            
            logger.info(f"📁 Tracked file upload session for user {user_id}")
            
        except Exception as e:
            logger.error(f"Failed to track file upload: {e}")
    
    @staticmethod
    async def award_custom_milestone(
        db: AsyncSession,
        user_id: UUID,
        milestone_type: str,
        subject: str,
        title: str,
        description: str,
        topic: Optional[str] = None,
        metadata: Optional[dict] = None
    ):
        """
        Manually award a milestone to a student.
        
        Use this for special achievements detected by the AI tutor, like:
        - First time solving a difficult problem independently
        - Showing creative problem-solving approach
        - Helping explain a concept clearly
        """
        try:
            milestone_data = MilestoneCreate(
                milestone_type=milestone_type,
                subject=subject,
                topic=topic,
                title=title,
                description=description,
                milestone_metadata=metadata or {}
            )
            
            milestone = await ProgressService.create_milestone(
                db=db,
                user_id=user_id,
                milestone_data=milestone_data
            )
            
            logger.info(f"🏆 Custom milestone awarded: {title} to user {user_id}")
            
            return milestone
            
        except Exception as e:
            logger.error(f"Failed to award milestone: {e}")


# ============= Integration with Chat Service =============

async def integrate_session_tracking_with_chat(
    db: AsyncSession,
    user_id: UUID,
    query: str,
    response: str,
    session_metadata: dict
):
    """
    Integration function to be called from chat service.
    
    Add this to mcp_host/services/chats.py in the chat_endpoint method:
    
    ```python
    # After successful chat response
    from mcp_host.services.session_tracker import SessionTracker
    
    await SessionTracker.track_chat_session(
        db=db,
        user_id=current_user.id,
        subject=inferred_subject,  # Extract from query or metadata
        topic=inferred_topic,
        difficulty_level=estimated_difficulty,
        questions_asked=1
    )
    ```
    """
    # Extract subject/topic from query or metadata
    subject = session_metadata.get("subject", "General")
    topic = session_metadata.get("topic", "Unknown")
    difficulty = session_metadata.get("difficulty_level", 5)
    
    await SessionTracker.track_chat_session(
        db=db,
        user_id=user_id,
        subject=subject,
        topic=topic,
        difficulty_level=difficulty,
        questions_asked=1
    )