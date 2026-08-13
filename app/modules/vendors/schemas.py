import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict


class VendorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    vendor_name: str
    display_name: str
    endpoint_url: str
    category: str
    is_public: bool
    last_check_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class VendorDetailResponse(VendorResponse):
    recent_status: str = "operational"


class VendorHistoryResponse(BaseModel):
    vendor_name: str
    uptime_percentage_24h: float = 99.99
    avg_latency_ms_24h: float = 45.0
    recent_checks_count: int = 288
