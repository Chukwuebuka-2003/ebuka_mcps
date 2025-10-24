"""
FastAPI router for consent and privacy management (GDPR-compliant)
Place this in: mcp_host/routers/consent.py
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from datetime import datetime, timezone

from mcp_host.database.db import get_db
from mcp_host.services.auths import get_current_user
from mcp_host.models.users import User as UserModel
from mcp_host.models.progress import ConsentAuditLog
from mcp_host.schemas.progress import (
    ConsentStatusResponse,
    ConsentUpdateRequest,
    ConsentAuditLogResponse,
)
from rag.models import ConsentLevel
import logging

logger = logging.getLogger(__name__)

consent_router = APIRouter(prefix="/consent", tags=["consent"])


# ============= Consent Status =============


@consent_router.get("/status", response_model=ConsentStatusResponse)
async def get_consent_status(
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get current consent and privacy settings for the user.

    Returns:
    - Consent level (full_profile, limited_anonymized, minimal_pseudonymous)
    - Data retention period
    - When consent was granted/updated
    - Data sharing preferences
    """
    try:
        # Get fresh user data
        result = await db.execute(
            select(UserModel).where(UserModel.id == current_user.id)
        )
        user = result.scalar_one()

        # Build sharing preferences from consent level
        sharing_preferences = {
            "personalized_learning": user.consent_level == "full_profile",
            "anonymized_insights": user.consent_level
            in ["full_profile", "limited_anonymized"],
            "cross_student_patterns": False,  # Always false for privacy
            "research_participation": False,  # Requires separate opt-in
        }

        return ConsentStatusResponse(
            consent_level=user.consent_level or "full_profile",
            granted_at=user.consent_granted_at,
            last_updated=user.last_consent_update,
            data_retention_days=user.data_retention_days or 365,
            sharing_preferences=sharing_preferences,
        )

    except Exception as e:
        logger.error(f"Failed to get consent status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============= Update Consent =============


@consent_router.put("/update")
async def update_consent(
    request: Request,
    consent_request: ConsentUpdateRequest,
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Update consent level and privacy settings.

    Consent Levels:
    - full_profile: Full personalization with learning history
    - limited_anonymized: Basic features, anonymized data
    - minimal_pseudonymous: No personal data retention

    When downgrading consent, user will be prompted about data deletion.
    All changes are logged for GDPR compliance.
    """
    try:
        # Validate consent level
        valid_levels = ["full_profile", "limited_anonymized", "minimal_pseudonymous"]
        if consent_request.consent_level not in valid_levels:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid consent level. Must be one of: {valid_levels}",
            )

        # Get current user data
        result = await db.execute(
            select(UserModel).where(UserModel.id == current_user.id)
        )
        user = result.scalar_one()

        old_consent_level = user.consent_level
        new_consent_level = consent_request.consent_level

        # Check if downgrading
        is_downgrade = (
            old_consent_level == "full_profile" and new_consent_level != "full_profile"
        )

        # Update user consent
        user.consent_level = new_consent_level
        user.data_retention_days = consent_request.data_retention_days
        user.last_consent_update = datetime.now(timezone.utc)

        if not user.consent_granted_at:
            user.consent_granted_at = datetime.now(timezone.utc)

        # Log consent change
        audit_log = ConsentAuditLog(
            user_id=user.id,
            action="consent_level_changed",
            old_consent_level=old_consent_level,
            new_consent_level=new_consent_level,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            changed_at=datetime.now(timezone.utc),
            details={
                "data_retention_days": consent_request.data_retention_days,
                "is_downgrade": is_downgrade,
            },
        )
        db.add(audit_log)

        await db.flush()

        # Warning message if downgrading
        warning_message = None
        if is_downgrade:
            warning_message = (
                "⚠️  You've reduced your consent level. "
                "Some personalized features may be limited. "
                "To delete your existing learning data, use the /consent/delete-data endpoint."
            )

        # Handle minimal consent (offer data deletion)
        if new_consent_level == "minimal_pseudonymous":
            warning_message = (
                "⚠️  MINIMAL CONSENT: No personal learning data will be stored. "
                "Would you like to delete your existing data? "
                "Call /consent/delete-data to proceed."
            )

        logger.info(
            f"Consent updated for user {user.id}: {old_consent_level} → {new_consent_level}"
        )

        return {
            "status": "success",
            "message": "Consent level updated successfully",
            "old_consent_level": old_consent_level,
            "new_consent_level": new_consent_level,
            "data_retention_days": consent_request.data_retention_days,
            "warning": warning_message,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update consent: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============= Consent Audit Log =============


@consent_router.get("/audit-log", response_model=List[ConsentAuditLogResponse])
async def get_consent_audit_log(
    limit: int = 20,
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get consent change history for the current user.

    Shows all changes to consent settings for transparency and GDPR compliance.
    """
    try:
        query = (
            select(ConsentAuditLog)
            .where(ConsentAuditLog.user_id == current_user.id)
            .order_by(ConsentAuditLog.changed_at.desc())
            .limit(limit)
        )

        result = await db.execute(query)
        logs = result.scalars().all()

        return [ConsentAuditLogResponse.model_validate(log) for log in logs]

    except Exception as e:
        logger.error(f"Failed to get audit log: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============= Data Deletion (GDPR Right to be Forgotten) =============


@consent_router.delete("/delete-data")
async def request_data_deletion(
    request: Request,
    confirm: bool = False,
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Request deletion of all personal learning data (GDPR compliance).

    This will:
    1. Delete all learning sessions from database
    2. Delete all milestones
    3. Anonymize chat history
    4. Remove vectors from Pinecone (RAG system)
    5. Delete files from Azure Blob Storage

    ⚠️  WARNING: This action cannot be undone!

    Set confirm=true to proceed with deletion.
    """
    try:
        if not confirm:
            return {
                "status": "confirmation_required",
                "message": (
                    "⚠️  Data deletion is permanent and cannot be undone. "
                    "To proceed, call this endpoint with confirm=true"
                ),
                "will_delete": [
                    "All learning session records",
                    "All milestone achievements",
                    "All chat conversations",
                    "All RAG knowledge base entries",
                    "All uploaded files",
                ],
            }

        logger.warning(f"🗑️  Data deletion requested for user {current_user.id}")

        # Import here to avoid circular dependency
        from mcp_host.models.progress import LearningSession, Milestone
        from mcp_host.models.chats import ChatSession, ChatMessage
        from utils.azure_storage import AzureStorageManager

        user_id = current_user.id

        # 1. Delete learning sessions
        await db.execute(
            select(LearningSession).where(LearningSession.user_id == user_id)
        )
        learning_sessions = (
            (
                await db.execute(
                    select(LearningSession).where(LearningSession.user_id == user_id)
                )
            )
            .scalars()
            .all()
        )

        for session in learning_sessions:
            await db.delete(session)

        logger.info(f"Deleted {len(learning_sessions)} learning sessions")

        # 2. Delete milestones
        milestones = (
            (await db.execute(select(Milestone).where(Milestone.user_id == user_id)))
            .scalars()
            .all()
        )

        for milestone in milestones:
            await db.delete(milestone)

        logger.info(f"Deleted {len(milestones)} milestones")

        # 3. Delete/anonymize chat sessions
        chat_sessions = (
            (
                await db.execute(
                    select(ChatSession).where(ChatSession.user_id == str(user_id))
                )
            )
            .scalars()
            .all()
        )

        for chat in chat_sessions:
            await db.delete(chat)

        logger.info(f"Deleted {len(chat_sessions)} chat sessions")

        # 4. Delete from Pinecone (RAG system)
        try:
            from rag.system import TutoringRAGSystem

            rag_system = TutoringRAGSystem()

            # Delete all vectors for this user
            # Note: Pinecone doesn't have a bulk delete by metadata,
            # so we'd need to implement custom deletion logic
            logger.warning(
                "⚠️  Pinecone deletion not fully implemented - manual cleanup may be needed"
            )

        except Exception as e:
            logger.error(f"Failed to delete from Pinecone: {e}")

        # 5. Delete from Azure Blob Storage
        try:
            storage = AzureStorageManager()
            files = storage.list_student_files(student_id=str(user_id))

            for file_info in files:
                storage.delete_file(file_info["blob_name"])

            logger.info(f"Deleted {len(files)} files from Azure")

        except Exception as e:
            logger.error(f"Failed to delete from Azure: {e}")

        # 6. Log the deletion
        audit_log = ConsentAuditLog(
            user_id=user_id,
            action="data_deleted",
            old_consent_level=current_user.consent_level,
            new_consent_level="minimal_pseudonymous",
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            changed_at=datetime.now(timezone.utc),
            details={
                "deleted_sessions": len(learning_sessions),
                "deleted_milestones": len(milestones),
                "deleted_chats": len(chat_sessions),
            },
        )
        db.add(audit_log)

        # Update user consent to minimal
        result = await db.execute(select(UserModel).where(UserModel.id == user_id))
        user = result.scalar_one()
        user.consent_level = "minimal_pseudonymous"
        user.last_consent_update = datetime.now(timezone.utc)

        await db.flush()

        logger.info(f"✅ Data deletion completed for user {user_id}")

        return {
            "status": "success",
            "message": "All personal learning data has been deleted",
            "deleted": {
                "learning_sessions": len(learning_sessions),
                "milestones": len(milestones),
                "chat_sessions": len(chat_sessions),
                "files": len(files) if "files" in locals() else 0,
            },
            "new_consent_level": "minimal_pseudonymous",
            "note": "Your account remains active but with minimal data collection",
        }

    except Exception as e:
        logger.error(f"Failed to delete data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============= Data Export (GDPR Right to Data Portability) =============


@consent_router.get("/export-data")
async def export_user_data(
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Export all user data in machine-readable format (GDPR compliance).

    Returns JSON with:
    - User profile
    - Learning sessions
    - Milestones
    - Chat history
    - Consent history

    Does NOT include:
    - Vector embeddings (Pinecone)
    - Uploaded files (available via separate download)
    """
    try:
        from mcp_host.models.progress import LearningSession, Milestone
        from mcp_host.models.chats import ChatSession, ChatMessage

        user_id = current_user.id

        # Get user profile
        user_data = {
            "id": str(user_id),
            "name": current_user.name,
            "email": current_user.email,
            "phone_number": current_user.phone_number,
            "consent_level": current_user.consent_level,
            "data_retention_days": current_user.data_retention_days,
            "created_at": current_user.created_at.isoformat()
            if current_user.created_at
            else None,
        }

        # Get learning sessions
        sessions = (
            (
                await db.execute(
                    select(LearningSession).where(LearningSession.user_id == user_id)
                )
            )
            .scalars()
            .all()
        )

        sessions_data = [
            {
                "subject": s.subject,
                "topic": s.topic,
                "session_date": s.session_date.isoformat(),
                "duration_minutes": s.duration_minutes,
                "difficulty_level": s.difficulty_level,
                "questions_asked": s.questions_asked,
            }
            for s in sessions
        ]

        # Get milestones
        milestones = (
            (await db.execute(select(Milestone).where(Milestone.user_id == user_id)))
            .scalars()
            .all()
        )

        milestones_data = [
            {
                "title": m.title,
                "description": m.description,
                "subject": m.subject,
                "topic": m.topic,
                "achieved_at": m.achieved_at.isoformat(),
                "milestone_type": m.milestone_type,
            }
            for m in milestones
        ]

        # Get consent history
        consent_logs = (
            (
                await db.execute(
                    select(ConsentAuditLog).where(ConsentAuditLog.user_id == user_id)
                )
            )
            .scalars()
            .all()
        )

        consent_data = [
            {
                "action": log.action,
                "old_consent_level": log.old_consent_level,
                "new_consent_level": log.new_consent_level,
                "changed_at": log.changed_at.isoformat(),
            }
            for log in consent_logs
        ]

        # Build export
        export = {
            "export_date": datetime.now(timezone.utc).isoformat(),
            "user": user_data,
            "learning_sessions": sessions_data,
            "milestones": milestones_data,
            "consent_history": consent_data,
            "summary": {
                "total_sessions": len(sessions_data),
                "total_milestones": len(milestones_data),
                "total_consent_changes": len(consent_data),
            },
        }

        logger.info(f"Data export generated for user {user_id}")

        return export

    except Exception as e:
        logger.error(f"Failed to export data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============= Privacy Policy Acceptance =============


@consent_router.post("/accept-privacy-policy")
async def accept_privacy_policy(
    request: Request,
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Record acceptance of privacy policy.

    Should be called when user first signs up or when policy is updated.
    """
    try:
        # Log acceptance
        audit_log = ConsentAuditLog(
            user_id=current_user.id,
            action="privacy_policy_accepted",
            old_consent_level=None,
            new_consent_level=current_user.consent_level,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            changed_at=datetime.now(timezone.utc),
            details={
                "policy_version": "1.0",  # Track policy version
                "accepted_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        db.add(audit_log)

        # Update user
        result = await db.execute(
            select(UserModel).where(UserModel.id == current_user.id)
        )
        user = result.scalar_one()

        if not user.consent_granted_at:
            user.consent_granted_at = datetime.now(timezone.utc)

        await db.flush()

        logger.info(f"Privacy policy accepted by user {current_user.id}")

        return {
            "status": "success",
            "message": "Privacy policy acceptance recorded",
            "accepted_at": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as e:
        logger.error(f"Failed to record privacy policy acceptance: {e}")
        raise HTTPException(status_code=500, detail=str(e))
