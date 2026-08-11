"""One-time API key issuance, authentication, and revocation."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from app.core.exceptions import NotFoundError, UnauthorizedError
from app.core.security import generate_api_key, hash_api_key
from app.modules.api_keys.repository import ApiKeyRepository
from app.modules.api_keys.schemas import (
    ApiKeyCreatedResponse,
    ApiKeyCreateRequest,
    ApiKeyIdentityDTO,
    ApiKeyResponse,
)


class ApiKeyService:
    def __init__(self, repository: ApiKeyRepository) -> None:
        self.repository = repository

    async def list(self, org_id: UUID) -> list[ApiKeyResponse]:
        return [ApiKeyResponse.model_validate(item) for item in await self.repository.list(org_id)]

    async def create(self, org_id: UUID, request: ApiKeyCreateRequest) -> ApiKeyCreatedResponse:
        plaintext, prefix, hashed = generate_api_key()
        values = request.model_dump()
        values.update({"org_id": org_id, "prefix": prefix, "hashed_key": hashed})
        model = await self.repository.create(values)
        return ApiKeyCreatedResponse(
            **ApiKeyResponse.model_validate(model).model_dump(), key=plaintext
        )

    async def revoke(self, org_id: UUID, key_id: UUID) -> None:
        model = await self.repository.get(org_id, key_id)
        if model is None:
            raise NotFoundError("API key not found")
        await self.repository.delete(model)

    async def authenticate(self, plaintext: str) -> ApiKeyIdentityDTO:
        model = await self.repository.by_hash(hash_api_key(plaintext))
        now = datetime.now(UTC)
        if model is None or (model.expires_at is not None and model.expires_at <= now):
            raise UnauthorizedError("Invalid or expired API key")
        await self.repository.touch(model, now)
        return ApiKeyIdentityDTO.model_validate(model, from_attributes=True)
