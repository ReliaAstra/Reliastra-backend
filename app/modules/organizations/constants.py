"""Organization roles and plans."""

from __future__ import annotations

from enum import StrEnum


class Plan(StrEnum):
    FREE = "free"
    STANDARD = "standard"
    PROFESSIONAL = "professional"
    AGENCY = "agency"


class MemberRole(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"
