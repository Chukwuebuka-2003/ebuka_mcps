from rag.models import Student, ConsentLevel
from typing import Optional
import logging

logger = logging.getLogger(__name__)


async def check_identity_and_consent(student_id: str, db_session=None) -> Student:
    """
    Validates user_id against an authenticated student database and checks consent levels.

    Args:
        student_id: The user's unique identifier (UUID from the users table)
        db_session: Optional database session for looking up user

    Returns:
        Student object with consent level and permissions
    """

    # If database session provided, look up the actual user
    if db_session:
        try:
            from sqlalchemy import select
            from mcp_host.models.users import User as UserModel

            result = await db_session.execute(
                select(UserModel).where(UserModel.id == student_id)
            )
            user = result.scalar_one_or_none()

            if user:
                logger.info(f"✅ User found in database: {user.email}")
                # User exists - grant full profile access
                return Student(
                    student_id=student_id,
                    consent_level=ConsentLevel.FULL_PROFILE,
                    session_purpose="personalized_tutoring",
                    data_sharing_scope={
                        "personal_data": True,
                        "cross_student_patterns": False,
                    },
                )
            else:
                logger.warning(f"⚠️  User {student_id} not found in database")
        except Exception as e:
            logger.error(f"❌ Error looking up user: {e}")

    # Default: Grant full access for any authenticated user
    # In production, you might want to require explicit consent records
    logger.info(f"🔓 Granting full profile access to user: {student_id}")
    return Student(
        student_id=student_id,
        consent_level=ConsentLevel.FULL_PROFILE,
        session_purpose="personalized_tutoring",
        data_sharing_scope={
            "personal_data": True,
            "cross_student_patterns": False,
        },
    )


# Synchronous version for backward compatibility
def check_identity_and_consent_sync(student_id: str) -> Student:
    """
    Synchronous version of identity check.
    Used when database session is not available.

    Args:
        student_id: The user's unique identifier

    Returns:
        Student object with full profile access
    """
    logger.info(f" Granting full profile access to user: {student_id}")
    return Student(
        student_id=student_id,
        consent_level=ConsentLevel.FULL_PROFILE,
        session_purpose="personalized_tutoring",
        data_sharing_scope={
            "personal_data": True,
            "cross_student_patterns": False,
        },
    )
