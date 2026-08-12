import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.organizations.agency_models import Application, Client


class AgencyRepository:
    # -- clients ------------------------------------------------------------

    @staticmethod
    async def list_clients(session: AsyncSession, org_id: uuid.UUID) -> list[Client]:
        stmt = (
            select(Client)
            .where(Client.org_id == org_id)
            .order_by(Client.created_at.asc())
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def get_client(
        session: AsyncSession, org_id: uuid.UUID, client_id: uuid.UUID
    ) -> Client | None:
        stmt = select(Client).where(
            Client.id == client_id, Client.org_id == org_id
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def create_client(
        session: AsyncSession, org_id: uuid.UUID, name: str, description: str | None
    ) -> Client:
        client = Client(org_id=org_id, name=name, description=description)
        session.add(client)
        await session.flush()
        return client

    @staticmethod
    async def update_client(
        session: AsyncSession, client: Client, **kwargs: Any
    ) -> Client:
        for key, value in kwargs.items():
            if value is not None and hasattr(client, key):
                setattr(client, key, value)
        session.add(client)
        await session.flush()
        return client

    @staticmethod
    async def delete_client(session: AsyncSession, client: Client) -> None:
        await session.delete(client)
        await session.flush()

    # -- applications ----------------------------------------------------------

    @staticmethod
    async def list_applications(
        session: AsyncSession, org_id: uuid.UUID, client_id: uuid.UUID | None = None
    ) -> list[Application]:
        stmt = select(Application).where(Application.org_id == org_id)
        if client_id:
            stmt = stmt.where(Application.client_id == client_id)
        stmt = stmt.order_by(Application.created_at.asc())
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def get_application(
        session: AsyncSession, org_id: uuid.UUID, app_id: uuid.UUID
    ) -> Application | None:
        stmt = select(Application).where(
            Application.id == app_id, Application.org_id == org_id
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def create_application(
        session: AsyncSession,
        org_id: uuid.UUID,
        name: str,
        description: str | None,
        client_id: uuid.UUID | None,
    ) -> Application:
        app = Application(
            org_id=org_id, name=name, description=description, client_id=client_id
        )
        session.add(app)
        await session.flush()
        return app

    @staticmethod
    async def update_application(
        session: AsyncSession, application: Application, **kwargs: Any
    ) -> Application:
        for key, value in kwargs.items():
            if value is not None and hasattr(application, key):
                setattr(application, key, value)
        session.add(application)
        await session.flush()
        return application

    @staticmethod
    async def delete_application(session: AsyncSession, application: Application) -> None:
        await session.delete(application)
        await session.flush()
