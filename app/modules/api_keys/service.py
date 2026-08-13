import uuid
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import ResourceNotFoundException, UnauthorizedException
from app.core.security import generate_api_key, hash_api_key
from app.modules.api_keys.models import ApiKey
from app.modules.api_keys.repository import ApiKeyRepository
from app.modules.api_keys.schemas import (
    ApiKeyCreateRequest,
    ApiKeyCreateResponse,
    ApiKeyResponse,
)


class ApiKeyService:
    def __init__(self, repository: ApiKeyRepository = ApiKeyRepository()) -> None:
        self.repository = repository

    async def list_keys(
        self, session: AsyncSession, org_id: uuid.UUID
    ) -> list[ApiKeyResponse]:
        keys = await self.repository.list_for_org(session, org_id)
        return [ApiKeyResponse.model_validate(k) for k in keys]

    async def create_key(
        self,
        session: AsyncSession,
        org_id: uuid.UUID,
        request: ApiKeyCreateRequest,
    ) -> ApiKeyCreateResponse:
        full_key, prefix, hashed_key = generate_api_key()
        api_key = await self.repository.create(
            session=session,
            org_id=org_id,
            name=request.name,
            prefix=prefix,
            hashed_key=hashed_key,
            scopes=request.scopes,
            expires_at=request.expires_at,
        )
        response_dict = ApiKeyResponse.model_validate(api_key).model_dump()
        response_dict["full_key"] = full_key
        return ApiKeyCreateResponse.model_validate(response_dict)

    async def revoke_key(
        self, session: AsyncSession, org_id: uuid.UUID, key_id: uuid.UUID
    ) -> None:
        key = await self.repository.get_by_id(session, key_id)
        if not key or key.org_id != org_id:
            raise ResourceNotFoundException("API key not found")
        await self.repository.delete(session, key)

    async def authenticate_key(
        self, session: AsyncSession, raw_key: str
    ) -> ApiKey:
        hashed_key = hash_api_key(raw_key)
        api_key = await self.repository.get_by_hashed_key(session, hashed_key)
        if not api_key:
            raise UnauthorizedException("Invalid API key")
        if api_key.expires_at and api_key.expires_at < datetime.now(
            timezone.utc
        ):
            raise UnauthorizedException("API key has expired")

        await self.repository.update_last_used(session, api_key)
        return api_key


api_key_service = ApiKeyService()
