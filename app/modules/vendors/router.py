"""Unauthenticated public vendor status routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.dependencies import get_vendor_service
from app.modules.vendors.schemas import VendorHistoryResponse, VendorResponse
from app.modules.vendors.service import VendorService

router = APIRouter(prefix="/v1/public/vendors", tags=["public vendors"])


@router.get("/", response_model=list[VendorResponse])
async def list_vendors(
    service: VendorService = Depends(get_vendor_service),
) -> list[VendorResponse]:
    return await service.list()


@router.get("/{vendor_name}", response_model=VendorResponse)
async def get_vendor(
    vendor_name: str, service: VendorService = Depends(get_vendor_service)
) -> VendorResponse:
    return await service.get(vendor_name)


@router.get("/{vendor_name}/history", response_model=VendorHistoryResponse)
async def vendor_history(
    vendor_name: str, service: VendorService = Depends(get_vendor_service)
) -> VendorHistoryResponse:
    return await service.history(vendor_name)
