"""Notification channel types."""

from __future__ import annotations

from enum import StrEnum


class ChannelType(StrEnum):
    EMAIL = "email"
    SLACK = "slack"
    PAGERDUTY = "pagerduty"
    WEBHOOK = "webhook"
