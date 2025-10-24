"""
Service layer for lifelong learning progress tracking
Place this in: mcp_host/services/progress.py
"""

from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, desc
from uuid import UUID
import logging

from mcp_host.models.progress import LearningSession, Milestone
from mcp_host.schemas.progress import (
    LearningSessionCreate,
    LearningSessionResponse,
    MilestoneCreate,
    MilestoneResponse,
    WeeklyActivity,
    ProgressReportResponse,
    KnowledgeRetentionAlert,
    TimelineEntry,
    LearningTimelineResponse,
    WeeklyDigestResponse,
)
from rag.system import TutoringRAGSystem
from rag.identity.checker import check_identity_and_consent_sync
from rag.types import MemoryType

logger = logging.getLogger(__name__)


class ProgressService:
    """Service for managing learning progress and analytics"""

    @staticmethod
    async def create_learning_session(
        db: AsyncSession, user_id: UUID, session_data: LearningSessionCreate
    ) -> LearningSessionResponse:
        """Create a new learning session record"""
        session = LearningSession(user_id=user_id, **session_data.model_dump())
        db.add(session)
        await db.flush()
        await db.refresh(session)
        return LearningSessionResponse.model_validate(session)

    @staticmethod
    async def create_milestone(
        db: AsyncSession, user_id: UUID, milestone_data: MilestoneCreate
    ) -> MilestoneResponse:
        """Create a new milestone achievement"""
        milestone = Milestone(user_id=user_id, **milestone_data.model_dump())
        db.add(milestone)
        await db.flush()
        await db.refresh(milestone)
        return MilestoneResponse.model_validate(milestone)

    @staticmethod
    async def get_user_milestones(
        db: AsyncSession, user_id: UUID, subject: Optional[str] = None, limit: int = 50
    ) -> List[MilestoneResponse]:
        """Get all milestones for a user"""
        query = select(Milestone).where(Milestone.user_id == user_id)

        if subject:
            query = query.where(Milestone.subject == subject)

        query = query.order_by(desc(Milestone.achieved_at)).limit(limit)

        result = await db.execute(query)
        milestones = result.scalars().all()

        return [MilestoneResponse.model_validate(m) for m in milestones]

    @staticmethod
    async def get_learning_sessions(
        db: AsyncSession,
        user_id: UUID,
        subject: Optional[str] = None,
        days_back: int = 30,
    ) -> List[LearningSessionResponse]:
        """Get learning sessions for a user"""
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_back)

        query = select(LearningSession).where(
            and_(
                LearningSession.user_id == user_id,
                LearningSession.session_date >= cutoff_date,
            )
        )

        if subject:
            query = query.where(LearningSession.subject == subject)

        query = query.order_by(desc(LearningSession.session_date))

        result = await db.execute(query)
        sessions = result.scalars().all()

        return [LearningSessionResponse.model_validate(s) for s in sessions]

    @staticmethod
    async def calculate_weekly_activity(
        db: AsyncSession, user_id: UUID, subject: str, days_back: int = 90
    ) -> List[WeeklyActivity]:
        """Calculate learning activity grouped by week"""
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_back)

        query = (
            select(LearningSession)
            .where(
                and_(
                    LearningSession.user_id == user_id,
                    LearningSession.subject == subject,
                    LearningSession.session_date >= cutoff_date,
                )
            )
            .order_by(LearningSession.session_date)
        )

        result = await db.execute(query)
        sessions = result.scalars().all()

        # Group by week
        weekly_data: Dict[int, List[LearningSession]] = {}

        for session in sessions:
            week_number = session.session_date.isocalendar()[1]
            if week_number not in weekly_data:
                weekly_data[week_number] = []
            weekly_data[week_number].append(session)

        # Build weekly activity summaries
        weekly_activities = []
        for week_num, week_sessions in sorted(weekly_data.items()):
            if not week_sessions:
                continue

            start_date = min(s.session_date for s in week_sessions)
            end_date = max(s.session_date for s in week_sessions)
            topics = list(set(s.topic for s in week_sessions))
            avg_difficulty = sum(s.difficulty_level or 0 for s in week_sessions) / len(
                week_sessions
            )
            total_time = sum(s.duration_minutes or 0 for s in week_sessions)

            weekly_activities.append(
                WeeklyActivity(
                    week_number=week_num,
                    start_date=start_date,
                    end_date=end_date,
                    total_interactions=len(week_sessions),
                    topics_covered=topics,
                    average_difficulty=round(avg_difficulty, 2),
                    total_study_time_minutes=total_time,
                )
            )

        return weekly_activities

    @staticmethod
    async def generate_progress_report(
        db: AsyncSession, user_id: UUID, subject: str, days_back: int = 30
    ) -> ProgressReportResponse:
        """Generate comprehensive progress report"""
        try:
            # Get data from database
            sessions = await ProgressService.get_learning_sessions(
                db, user_id, subject, days_back
            )
            milestones = await ProgressService.get_user_milestones(db, user_id, subject)
            weekly_activity = await ProgressService.calculate_weekly_activity(
                db, user_id, subject, days_back
            )

            # Get RAG system trajectory data
            rag_system = TutoringRAGSystem()
            trajectory = rag_system.analyze_learning_trajectory(
                student_id=str(user_id), subject=subject, days_back=days_back
            )

            # Calculate metrics
            total_study_time = sum(s.duration_minutes or 0 for s in sessions)
            topics_covered = list(set(s.topic for s in sessions))
            difficulty_levels = [
                s.difficulty_level for s in sessions if s.difficulty_level
            ]

            # Find most active periods
            most_active = sorted(
                weekly_activity, key=lambda w: w.total_interactions, reverse=True
            )[:3]
            most_active_periods = [
                f"Week of {w.start_date.strftime('%B %d')}" for w in most_active
            ]

            # Analyze performance
            strengths, improvements = ProgressService._analyze_performance(
                sessions, milestones, trajectory
            )

            # Generate recommendations
            recommendations = ProgressService._generate_recommendations(
                trajectory, topics_covered
            )

            # Check for topics needing review
            topics_to_review = await ProgressService._check_knowledge_retention(
                db, user_id, subject
            )

            return ProgressReportResponse(
                student_id=str(user_id),
                subject=subject,
                time_period_days=days_back,
                generated_at=datetime.now(timezone.utc),
                total_interactions=trajectory["total_interactions"],
                skill_assessments=trajectory["skill_assessments"],
                error_patterns=trajectory["error_patterns"],
                success_milestones=trajectory["success_milestones"],
                topics_covered=topics_covered,
                difficulty_progression=difficulty_levels,
                weekly_activity=weekly_activity,
                most_active_periods=most_active_periods,
                total_study_time_minutes=total_study_time,
                strengths=strengths,
                areas_for_improvement=improvements,
                recommended_next_topics=recommendations,
                topics_needing_review=topics_to_review,
            )

        except Exception as e:
            logger.error(f"Error generating progress report: {e}")
            raise

    @staticmethod
    async def get_learning_timeline(
        user_id: UUID, subject: Optional[str] = None, days_back: int = 90
    ) -> LearningTimelineResponse:
        """Get chronological timeline of learning events from RAG system"""
        try:
            rag_system = TutoringRAGSystem()
            student = check_identity_and_consent_sync(str(user_id))

            # Retrieve all interactions
            nodes, _ = rag_system.retrieve_student_context(
                student=student,
                current_topic=subject or "learning",
                subject=subject,
                memory_types=None,  # Get all types
                limit=100,
                similarity_threshold=0.0,  # Get everything
            )

            # Sort by timestamp (oldest first)
            nodes.sort(key=lambda n: n.metadata.get("timestamp", ""), reverse=False)

            # Build timeline
            timeline = []
            for node in nodes:
                timestamp_str = node.metadata.get("timestamp")
                if not timestamp_str:
                    continue

                timeline.append(
                    TimelineEntry(
                        timestamp=datetime.fromisoformat(timestamp_str),
                        topic=node.metadata.get("topic", "Unknown"),
                        memory_type=node.metadata.get("memory_type", "unknown"),
                        difficulty_level=node.metadata.get("difficulty_level", 0),
                        content_preview=node.text[:200],
                        document_title=node.metadata.get("document_title"),
                    )
                )

            # Calculate time range
            time_range = {
                "start": timeline[0].timestamp
                if timeline
                else datetime.now(timezone.utc),
                "end": timeline[-1].timestamp
                if timeline
                else datetime.now(timezone.utc),
            }

            return LearningTimelineResponse(
                student_id=str(user_id),
                subject=subject,
                time_range=time_range,
                total_events=len(timeline),
                timeline=timeline,
            )

        except Exception as e:
            logger.error(f"Error generating timeline: {e}")
            raise

    @staticmethod
    async def generate_weekly_digest(
        db: AsyncSession, user_id: UUID
    ) -> WeeklyDigestResponse:
        """Generate weekly learning summary"""
        week_start = datetime.now(timezone.utc) - timedelta(days=7)
        week_end = datetime.now(timezone.utc)

        # Get sessions from the past week
        query = select(LearningSession).where(
            and_(
                LearningSession.user_id == user_id,
                LearningSession.session_date >= week_start,
            )
        )
        result = await db.execute(query)
        sessions = result.scalars().all()

        # Get milestones from the past week
        milestone_query = select(Milestone).where(
            and_(Milestone.user_id == user_id, Milestone.achieved_at >= week_start)
        )
        milestone_result = await db.execute(milestone_query)
        milestones = milestone_result.scalars().all()

        # Calculate metrics
        topics_learned = list(set(s.topic for s in sessions))
        total_time = sum(s.duration_minutes or 0 for s in sessions)
        questions_count = sum(s.questions_asked for s in sessions)

        # Calculate learning streak
        streak = await ProgressService._calculate_learning_streak(db, user_id)

        # Build summary
        summary = {
            "topics_learned": topics_learned,
            "total_study_time": f"{total_time // 60}h {total_time % 60}m",
            "questions_asked": questions_count,
            "sessions_completed": len(sessions),
            "difficulty_progression": "+2 levels" if sessions else "No change",
        }

        achievements = [f"🎉 {m.title}" for m in milestones]

        if streak >= 5:
            achievements.append(f"🔥 {streak}-day learning streak!")

        # Check retention
        retention_alerts = await ProgressService._check_knowledge_retention(
            db, user_id, None
        )

        retention_checks = [
            KnowledgeRetentionAlert(
                topic=alert["topic"],
                subject=alert["subject"],
                last_studied=alert["last_studied"],
                days_since_review=alert["days_since"],
                retention_risk=alert["risk"],
                recommendation=alert["recommendation"],
            )
            for alert in retention_alerts[:3]  # Top 3
        ]

        # Generate next week goals
        next_goals = ProgressService._generate_next_week_goals(sessions, milestones)

        return WeeklyDigestResponse(
            week_start=week_start,
            week_end=week_end,
            summary=summary,
            achievements=achievements,
            retention_checks=retention_checks,
            next_week_goals=next_goals,
            learning_streak_days=streak,
        )

    # ============= Helper Methods =============

    @staticmethod
    def _analyze_performance(
        sessions: List[LearningSessionResponse],
        milestones: List[MilestoneResponse],
        trajectory: Dict,
    ) -> tuple[List[str], List[str]]:
        """Analyze strengths and areas for improvement"""
        strengths = []
        improvements = []

        # Check milestone achievements
        if len(milestones) > 3:
            strengths.append(f"🏆 Achieved {len(milestones)} milestones")

        # Check success vs error ratio
        if trajectory["success_milestones"] > trajectory["error_patterns"]:
            strengths.append("✅ Consistent progress with few errors")
        elif trajectory["error_patterns"] > 5:
            improvements.append("📚 Review common mistake patterns")

        # Check study consistency
        if len(sessions) >= 20:
            strengths.append("💪 Excellent study consistency")
        elif len(sessions) < 5:
            improvements.append("📅 Try to study more regularly")

        # Check difficulty progression
        if sessions:
            avg_difficulty = sum(s.difficulty_level or 0 for s in sessions) / len(
                sessions
            )
            if avg_difficulty > 7:
                strengths.append("🚀 Working on advanced material")
            elif avg_difficulty < 4:
                improvements.append("⬆️  Ready to tackle harder challenges")

        return strengths, improvements

    @staticmethod
    def _generate_recommendations(
        trajectory: Dict, topics_covered: List[str]
    ) -> List[str]:
        """Generate personalized recommendations"""
        recommendations = []

        covered_set = set(topics_covered)

        # Subject-specific recommendations
        if "Algebra" in covered_set and "Calculus" not in covered_set:
            recommendations.append("📐 Introduction to Calculus - You're ready!")

        if "Calculus" in covered_set and "Differential Equations" not in covered_set:
            recommendations.append("🧮 Differential Equations")

        # Based on difficulty progression
        if trajectory["difficulty_progression"]:
            avg_diff = sum(trajectory["difficulty_progression"]) / len(
                trajectory["difficulty_progression"]
            )
            if avg_diff < 5:
                recommendations.append("⬆️  Try intermediate-level problems")

        # Generic recommendations if none generated
        if not recommendations:
            recommendations.append("🔍 Explore related topics to deepen understanding")
            recommendations.append("🎯 Set specific learning goals for next week")

        return recommendations

    @staticmethod
    async def _check_knowledge_retention(
        db: AsyncSession, user_id: UUID, subject: Optional[str]
    ) -> List[Dict[str, Any]]:
        """Check which topics need review based on time since last study"""
        # Get topics studied more than 30 days ago
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=30)

        query = (
            select(
                LearningSession.topic,
                LearningSession.subject,
                func.max(LearningSession.session_date).label("last_studied"),
            )
            .where(LearningSession.user_id == user_id)
            .group_by(LearningSession.topic, LearningSession.subject)
        )

        if subject:
            query = query.where(LearningSession.subject == subject)

        result = await db.execute(query)
        topics = result.all()

        needs_review = []
        for topic, subj, last_studied in topics:
            if last_studied < cutoff_date:
                days_since = (datetime.now(timezone.utc) - last_studied).days

                risk = "low"
                if days_since > 60:
                    risk = "high"
                elif days_since > 45:
                    risk = "medium"

                needs_review.append(
                    {
                        "topic": topic,
                        "subject": subj,
                        "last_studied": last_studied,
                        "days_since": days_since,
                        "risk": risk,
                        "recommendation": f"Quick 10-minute review recommended",
                    }
                )

        # Sort by days since (highest first)
        needs_review.sort(key=lambda x: x["days_since"], reverse=True)

        return needs_review

    @staticmethod
    async def _calculate_learning_streak(db: AsyncSession, user_id: UUID) -> int:
        """Calculate consecutive days with learning activity"""
        # Get sessions from last 30 days
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)

        query = (
            select(LearningSession.session_date)
            .where(
                and_(
                    LearningSession.user_id == user_id,
                    LearningSession.session_date >= cutoff,
                )
            )
            .order_by(desc(LearningSession.session_date))
        )

        result = await db.execute(query)
        dates = [row[0].date() for row in result.all()]

        if not dates:
            return 0

        # Count consecutive days
        streak = 1
        current_date = dates[0]

        for i in range(1, len(dates)):
            expected_date = current_date - timedelta(days=1)
            if dates[i] == expected_date:
                streak += 1
                current_date = dates[i]
            elif dates[i] < expected_date:
                break

        return streak

    @staticmethod
    def _generate_next_week_goals(
        sessions: List[LearningSessionResponse], milestones: List[MilestoneResponse]
    ) -> List[str]:
        """Generate suggested goals for next week"""
        goals = []

        if sessions:
            # Continuation goals
            recent_topics = list(set(s.topic for s in sessions[:5]))
            if recent_topics:
                goals.append(f"Complete advanced problems in {recent_topics[0]}")

        # Milestone-based goals
        if len(milestones) < 2:
            goals.append("🎯 Achieve your first milestone this week")

        # Consistency goals
        if len(sessions) < 5:
            goals.append("📅 Study at least 5 times this week")
        else:
            goals.append("🔥 Maintain your learning streak")

        # Growth goals
        goals.append("⬆️  Tackle one challenging problem")

        return goals[:4]  # Return top 4 goals
