from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rate_limit import SlidingWindowRateLimiter, enforce_rate_limit, public_vendor_limiter
from app.db.session import get_db
from app.modules.vendors.schemas import (
    VendorDeveloperResponse,
    VendorDetailResponse,
    VendorHistoryResponse,
    VendorIncidentsResponse,
    VendorMetricsResponse,
    VendorResponse,
    VendorTimelineResponse,
)
from app.modules.vendors.service import VendorService, vendor_service

router = APIRouter(prefix="/v1/public/vendors", tags=["Public Vendors"])

developer_limiter = SlidingWindowRateLimiter(
    limit=30, window_seconds=60, key_prefix="rl_developer"
)


def get_vnd_service() -> VendorService:
    return vendor_service


async def _rate_limit(request: Request) -> None:
    await enforce_rate_limit(request, public_vendor_limiter)


@router.get("", response_model=list[VendorResponse])
async def list_public_vendors(
    request: Request,
    db: AsyncSession = Depends(get_db),
    service: VendorService = Depends(get_vnd_service),
) -> list[VendorResponse]:
    await _rate_limit(request)
    return await service.list_public_vendors(db)


@router.get("/{vendor_name}", response_model=VendorDetailResponse)
async def get_public_vendor(
    request: Request,
    vendor_name: str,
    db: AsyncSession = Depends(get_db),
    service: VendorService = Depends(get_vnd_service),
) -> VendorDetailResponse:
    await _rate_limit(request)
    return await service.get_vendor_detail(db, vendor_name)


@router.get("/{vendor_name}/history", response_model=VendorHistoryResponse)
async def get_public_vendor_history(
    request: Request,
    vendor_name: str,
    db: AsyncSession = Depends(get_db),
    service: VendorService = Depends(get_vnd_service),
) -> VendorHistoryResponse:
    await _rate_limit(request)
    return await service.get_vendor_history(db, vendor_name)


@router.get("/{vendor_name}/metrics", response_model=VendorMetricsResponse)
async def get_vendor_metrics(
    request: Request,
    vendor_name: str,
    window: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    service: VendorService = Depends(get_vnd_service),
) -> VendorMetricsResponse:
    await _rate_limit(request)
    return await service.get_vendor_metrics(db, vendor_name, window)


@router.get("/{vendor_name}/timeline", response_model=VendorTimelineResponse)
async def get_vendor_timeline(
    request: Request,
    vendor_name: str,
    window: str = Query(default="24h"),
    resolution: str = Query(default="auto"),
    region: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    service: VendorService = Depends(get_vnd_service),
) -> VendorTimelineResponse:
    await _rate_limit(request)
    return await service.get_vendor_timeline(
        db, vendor_name, window, resolution, region
    )


@router.get("/{vendor_name}/incidents", response_model=VendorIncidentsResponse)
async def get_vendor_incidents(
    request: Request,
    vendor_name: str,
    limit: int = Query(default=50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    service: VendorService = Depends(get_vnd_service),
) -> VendorIncidentsResponse:
    await _rate_limit(request)
    return await service.get_vendor_incidents(db, vendor_name, limit)


@router.get("/{vendor_name}/developer", response_model=VendorDeveloperResponse)
async def get_vendor_developer_info(
    request: Request,
    vendor_name: str,
    db: AsyncSession = Depends(get_db),
    service: VendorService = Depends(get_vnd_service),
) -> VendorDeveloperResponse:
    await enforce_rate_limit(request, developer_limiter)
    return await service.get_developer_info(db, vendor_name)
