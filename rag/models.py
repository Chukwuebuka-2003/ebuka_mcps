from dataclasses import dataclass
from enum import Enum
from typing import Optional


class ConsentLevel(Enum):
    FULL_PROFILE = "full_profile"
    LIMITED_ANONYMIZED = "limited_anonymized"
    MINIMAL_PSEUDONYMOUS = "minimal_pseudonymous"


@dataclass
class Student:
    student_id: str
    consent_level: ConsentLevel
    session_purpose: Optional[str] = None
    data_sharing_scope: Optional[dict] = None
