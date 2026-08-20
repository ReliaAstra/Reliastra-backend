from __future__ import annotations

import logging

from app.config import settings

logger = logging.getLogger(__name__)


async def seed_first_admin() -> None:
    """If FIRST_ADMIN_EMAIL is set and user exists, set is_system_admin=True.

    Called during application startup (lifespan) to bootstrap the first
    system admin from an environment variable, so the admin panel is
    accessible without manual DB edits.
    """
    email = settings.FIRST_ADMIN_EMAIL
    if not email:
        logger.info("FIRST_ADMIN_EMAIL not set — skipping admin seed")
        return

    from app.db.session import get_session_maker
    from app.modules.users.repository import UserRepository

    session_maker = get_session_maker()
    async with session_maker() as session:
        try:
            user = await UserRepository.get_by_email(session, email)
            if not user:
                logger.warning(
                    "FIRST_ADMIN_EMAIL=%s — user not found, skipping admin promotion",
                    email,
                )
                return

            if user.is_system_admin:
                logger.info(
                    "FIRST_ADMIN_EMAIL=%s — user already is_system_admin, skipping",
                    email,
                )
                return

            await UserRepository.update(session, user, is_system_admin=True)
            await session.commit()
            logger.info(
                "Promoted %s (%s) to is_system_admin via FIRST_ADMIN_EMAIL",
                user.full_name,
                user.email,
            )
        except Exception as exc:
            logger.error("Failed to seed first admin: %s", exc)
            await session.rollback()
