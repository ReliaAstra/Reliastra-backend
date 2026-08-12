from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.rate_limit import public_vendor_limiter, enforce_rate_limit
from app.db.session import get_db
from app.modules.vendors.intel_schemas import (
    VendorIncidentResponse,
    VendorMetricsResponse,
)
from app.modules.vendors.intel_service import vendor_intel_service
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


@router.get("/{slug}/metrics", response_model=VendorMetricsResponse)
async def get_public_vendor_metrics(
    request: Request,
    slug: str,
    days: int = Query(default=90, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
) -> VendorMetricsResponse:
    await enforce_rate_limit(request, public_vendor_limiter)
    return await vendor_intel_service.get_metrics(db, slug, days=days)


@router.get("/{slug}/incidents", response_model=list[VendorIncidentResponse])
async def get_public_vendor_incidents(
    request: Request,
    slug: str,
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> list[VendorIncidentResponse]:
    await enforce_rate_limit(request, public_vendor_limiter)
    return await vendor_intel_service.list_incidents(db, slug, limit=limit)
