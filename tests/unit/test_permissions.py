from __future__ import annotations

import pytest

from app.core.exceptions import ForbiddenError
from app.core.permissions import Role, ensure_role


def test_role_hierarchy() -> None:
    ensure_role(Role.OWNER, Role.ADMIN)
    ensure_role(Role.MEMBER, Role.MEMBER)
    with pytest.raises(ForbiddenError):
        ensure_role(Role.VIEWER, Role.MEMBER)
