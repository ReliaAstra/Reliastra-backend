import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.agencies.models import Application, Client


class AgencyRepository:
    @staticmethod
    async def get_client(
        session: AsyncSession, client_id: uuid.UUID
    ) -> Client | None:
        result = await session.execute(
            select(Client).where(Client.id == client_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_clients(
        session: AsyncSession, org_id: uuid.UUID
    ) -> list[Client]:
        result = await session.execute(
            select(Client)
            .where(Client.org_id == org_id)
            .order_by(Client.name.asc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def create_client(
        session: AsyncSession,
        org_id: uuid.UUID,
        name: str,
        description: str | None = None,
    ) -> Client:
        client = Client(org_id=org_id, name=name, description=description)
        session.add(client)
        await session.flush()
        return client

    @staticmethod
    async def get_application(
        session: AsyncSession, application_id: uuid.UUID
    ) -> Application | None:
        result = await session.execute(
            select(Application).where(Application.id == application_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_default_application(
        session: AsyncSession, org_id: uuid.UUID
    ) -> Application | None:
        result = await session.execute(
            select(Application)
            .where(
                Application.org_id == org_id,
                Application.client_id.is_(None),
                Application.name == "Default",
            )
            .order_by(Application.created_at.asc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_applications(
        session: AsyncSession,
        org_id: uuid.UUID,
        client_id: uuid.UUID,
    ) -> list[Application]:
        result = await session.execute(
            select(Application)
            .where(
                Application.org_id == org_id,
                Application.client_id == client_id,
            )
            .order_by(Application.name.asc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def create_application(
        session: AsyncSession,
        org_id: uuid.UUID,
        name: str,
        client_id: uuid.UUID | None = None,
        description: str | None = None,
    ) -> Application:
        application = Application(
            org_id=org_id,
            client_id=client_id,
            name=name,
            description=description,
        )
        session.add(application)
        await session.flush()
        return application
