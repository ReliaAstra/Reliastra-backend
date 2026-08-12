from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.rate_limit import public_vendor_limiter, enforce_rate_limit
from app.db.session import get_db
from app.modules.vendors.schemas import (
    VendorDetailResponse,
    VendorHistoryResponse,
    VendorResponse,
)
from app.modules.vendors.service import VendorService, vendor_service

router = APIRouter(prefix="/v1/public/vendors", tags=["Public Vendors"])


def get_vnd_service() -> VendorService:
    return vendor_service


@router.get("", response_model=list[VendorResponse])
async def list_public_vendors(
    request: Request,
    db: AsyncSession = Depends(get_db),
    service: VendorService = Depends(get_vnd_service),
) -> list[VendorResponse]:
    await enforce_rate_limit(request, public_vendor_limiter)
    return await service.list_public_vendors(db)


@router.get("/{vendor_name}", response_model=VendorDetailResponse)
async def get_public_vendor(
    request: Request,
    vendor_name: str,
    db: AsyncSession = Depends(get_db),
    service: VendorService = Depends(get_vnd_service),
) -> VendorDetailResponse:
    await enforce_rate_limit(request, public_vendor_limiter)
    return await service.get_vendor_detail(db, vendor_name)


@router.get("/{vendor_name}/history", response_model=VendorHistoryResponse)
async def get_public_vendor_history(
    request: Request,
    vendor_name: str,
    db: AsyncSession = Depends(get_db),
    service: VendorService = Depends(get_vnd_service),
) -> VendorHistoryResponse:
    await enforce_rate_limit(request, public_vendor_limiter)
    return await service.get_vendor_history(db, vendor_name)
