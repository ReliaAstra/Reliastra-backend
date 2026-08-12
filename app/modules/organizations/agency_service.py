import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ResourceNotFoundException
from app.modules.organizations.agency_repository import AgencyRepository
from app.modules.organizations.agency_schemas import (
    ApplicationCreateRequest,
    ApplicationResponse,
    ApplicationUpdateRequest,
    ClientCreateRequest,
    ClientResponse,
    ClientUpdateRequest,
)


class AgencyService:
    def __init__(self, repository: AgencyRepository = AgencyRepository()) -> None:
        self.repository = repository

    # -- clients --------------------------------------------------------------

    async def list_clients(
        self, session: AsyncSession, org_id: uuid.UUID
    ) -> list[ClientResponse]:
        clients = await self.repository.list_clients(session, org_id)
        return [ClientResponse.model_validate(c) for c in clients]

    async def get_client(
        self, session: AsyncSession, org_id: uuid.UUID, client_id: uuid.UUID
    ) -> ClientResponse:
        client = await self.repository.get_client(session, org_id, client_id)
        if not client:
            raise ResourceNotFoundException("Client not found")
        return ClientResponse.model_validate(client)

    async def create_client(
        self, session: AsyncSession, org_id: uuid.UUID, request: ClientCreateRequest
    ) -> ClientResponse:
        client = await self.repository.create_client(
            session, org_id, request.name, request.description
        )
        return ClientResponse.model_validate(client)

    async def update_client(
        self,
        session: AsyncSession,
        org_id: uuid.UUID,
        client_id: uuid.UUID,
        request: ClientUpdateRequest,
    ) -> ClientResponse:
        client = await self.repository.get_client(session, org_id, client_id)
        if not client:
            raise ResourceNotFoundException("Client not found")
        client = await self.repository.update_client(
            session, client, name=request.name, description=request.description
        )
        return ClientResponse.model_validate(client)

    async def delete_client(
        self, session: AsyncSession, org_id: uuid.UUID, client_id: uuid.UUID
    ) -> None:
        client = await self.repository.get_client(session, org_id, client_id)
        if not client:
            raise ResourceNotFoundException("Client not found")
        await self.repository.delete_client(session, client)

    # -- applications ----------------------------------------------------------

    async def list_applications(
        self,
        session: AsyncSession,
        org_id: uuid.UUID,
        client_id: uuid.UUID | None = None,
    ) -> list[ApplicationResponse]:
        apps = await self.repository.list_applications(session, org_id, client_id)
        return [ApplicationResponse.model_validate(a) for a in apps]

    async def get_application(
        self, session: AsyncSession, org_id: uuid.UUID, app_id: uuid.UUID
    ) -> ApplicationResponse:
        app = await self.repository.get_application(session, org_id, app_id)
        if not app:
            raise ResourceNotFoundException("Application not found")
        return ApplicationResponse.model_validate(app)

    async def create_application(
        self,
        session: AsyncSession,
        org_id: uuid.UUID,
        request: ApplicationCreateRequest,
    ) -> ApplicationResponse:
        if request.client_id:
            client = await self.repository.get_client(session, org_id, request.client_id)
            if not client:
                raise ResourceNotFoundException("Client not found")
        app = await self.repository.create_application(
            session, org_id, request.name, request.description, request.client_id
        )
        return ApplicationResponse.model_validate(app)

    async def update_application(
        self,
        session: AsyncSession,
        org_id: uuid.UUID,
        app_id: uuid.UUID,
        request: ApplicationUpdateRequest,
    ) -> ApplicationResponse:
        app = await self.repository.get_application(session, org_id, app_id)
        if not app:
            raise ResourceNotFoundException("Application not found")
        app = await self.repository.update_application(
            session,
            app,
            name=request.name,
            description=request.description,
            client_id=request.client_id,
        )
        return ApplicationResponse.model_validate(app)

    async def delete_application(
        self, session: AsyncSession, org_id: uuid.UUID, app_id: uuid.UUID
    ) -> None:
        app = await self.repository.get_application(session, org_id, app_id)
        if not app:
            raise ResourceNotFoundException("Application not found")
        await self.repository.delete_application(session, app)


agency_service = AgencyService()
