"""Organization API key management routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Response

from app.core.permissions import Role
from app.dependencies import OrgContext, get_api_key_service, org_context
from app.modules.api_keys.schemas import ApiKeyCreatedResponse, ApiKeyCreateRequest, ApiKeyResponse
from app.modules.api_keys.service import ApiKeyService

router = APIRouter(prefix="/v1/orgs/{org_id}/api-keys", tags=["api keys"])


@router.get("/", response_model=list[ApiKeyResponse])
async def list_keys(
    org_id: UUID,
    _context: OrgContext = Depends(org_context(Role.ADMIN)),
    service: ApiKeyService = Depends(get_api_key_service),
) -> list[ApiKeyResponse]:
    return await service.list(org_id)


@router.post("/", response_model=ApiKeyCreatedResponse, status_code=201)
async def create_key(
    org_id: UUID,
    payload: ApiKeyCreateRequest,
    _context: OrgContext = Depends(org_context(Role.ADMIN)),
    service: ApiKeyService = Depends(get_api_key_service),
) -> ApiKeyCreatedResponse:
    return await service.create(org_id, payload)


@router.delete("/{key_id}", status_code=204)
async def revoke_key(
    org_id: UUID,
    key_id: UUID,
    _context: OrgContext = Depends(org_context(Role.ADMIN)),
    service: ApiKeyService = Depends(get_api_key_service),
) -> Response:
    await service.revoke(org_id, key_id)
    return Response(status_code=204)
