import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ResourceNotFoundException
from app.modules.agencies.repository import AgencyRepository
from app.modules.agencies.schemas import (
    ApplicationCreateRequest,
    ApplicationResponse,
    ClientCreateRequest,
    ClientResponse,
)
from app.modules.organizations.repository import OrganizationRepository


class AgencyService:
    def __init__(
        self, repository: AgencyRepository = AgencyRepository()
    ) -> None:
        self.repository = repository

    @staticmethod
    async def _require_org(session: AsyncSession, org_id: uuid.UUID):
        org = await OrganizationRepository.get_by_id(session, org_id)
        if not org:
            raise ResourceNotFoundException("Organization not found")
        return org

    async def list_clients(
        self, session: AsyncSession, org_id: uuid.UUID
    ) -> list[ClientResponse]:
        await self._require_org(session, org_id)
        rows = await self.repository.list_clients(session, org_id)
        return [ClientResponse.model_validate(row) for row in rows]

    async def create_client(
        self,
        session: AsyncSession,
        org_id: uuid.UUID,
        request: ClientCreateRequest,
    ) -> ClientResponse:
        org = await self._require_org(session, org_id)
        client = await self.repository.create_client(
            session, org_id, request.name, request.description
        )
        if not org.has_agency_mode:
            await OrganizationRepository.update(
                session, org, has_agency_mode=True
            )
        return ClientResponse.model_validate(client)

    async def list_applications(
        self,
        session: AsyncSession,
        org_id: uuid.UUID,
        client_id: uuid.UUID,
    ) -> list[ApplicationResponse]:
        await self._require_client(session, org_id, client_id)
        rows = await self.repository.list_applications(
            session, org_id, client_id
        )
        return [ApplicationResponse.model_validate(row) for row in rows]

    async def create_application(
        self,
        session: AsyncSession,
        org_id: uuid.UUID,
        client_id: uuid.UUID,
        request: ApplicationCreateRequest,
    ) -> ApplicationResponse:
        await self._require_client(session, org_id, client_id)
        application = await self.repository.create_application(
            session,
            org_id=org_id,
            client_id=client_id,
            name=request.name,
            description=request.description,
        )
        return ApplicationResponse.model_validate(application)

    async def _require_client(
        self,
        session: AsyncSession,
        org_id: uuid.UUID,
        client_id: uuid.UUID,
    ):
        client = await self.repository.get_client(session, client_id)
        if not client or client.org_id != org_id:
            raise ResourceNotFoundException("Client not found")
        return client


agency_service = AgencyService()
