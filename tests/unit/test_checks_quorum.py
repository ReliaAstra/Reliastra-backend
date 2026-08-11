from __future__ import annotations

from dataclasses import dataclass

from app.modules.checks.service import CheckService


@dataclass
class Result:
    region: str
    is_up: bool


def test_recovery_requires_two_consecutive_successes_in_two_regions() -> None:
    confirmed = [
        Result("us-east", True),
        Result("us-east", True),
        Result("eu-west", True),
        Result("eu-west", True),
    ]
    unconfirmed = [
        Result("us-east", True),
        Result("us-east", True),
        Result("eu-west", True),
        Result("eu-west", False),
    ]
    assert CheckService._recovery_confirmed(confirmed)
    assert not CheckService._recovery_confirmed(unconfirmed)
