import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class VendorEndpointResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    endpoint_url: str
    regions: list[str]
    health_status: str
    is_active: bool
    last_check_at: datetime | None = None


class VendorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    vendor_name: str
    display_name: str
    category: str
    is_public: bool
    last_check_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class VendorDetailResponse(VendorResponse):
    recent_status: str = "unknown"
    endpoints: list[VendorEndpointResponse] = Field(default_factory=list)


class VendorHistoryResponse(BaseModel):
    vendor_name: str
    uptime_percentage_24h: float
    avg_latency_ms_24h: float
    recent_checks_count: int


class VendorWindowMetrics(BaseModel):
    window: str
    total_observations: int
    uptime_percentage: float
    avg_latency_ms: float
    p95_latency_ms: float | None = None


class VendorMetricsResponse(BaseModel):
    vendor_name: str
    metrics: dict[str, VendorWindowMetrics]


class VendorIncidentResponse(BaseModel):
    incident_id: uuid.UUID
    dependency_name: str
    started_at: datetime
    resolved_at: datetime | None
    severity: str
    status: str
    duration_seconds: float | None


class VendorIncidentsResponse(BaseModel):
    vendor_name: str
    incidents: list[VendorIncidentResponse]


# ---------------------------------------------------------------------------
# Timeline endpoint schemas
# ---------------------------------------------------------------------------


class TimelineBucket(BaseModel):
    """A single aggregated time bucket in the vendor timeline."""

    timestamp: datetime
    avg_latency_ms: float
    status_code: int | None
    is_up: bool
    observation_count: int
    incident_id: uuid.UUID | None = None


class TimelineCurrent(BaseModel):
    """The most recent observation for a vendor, independent of the window."""

    timestamp: datetime | None = None
    latency_ms: float | None = None
    status_code: int | None = None
    is_up: bool | None = None


class VendorTimelineResponse(BaseModel):
    """Full response for GET /v1/public/vendors/{vendor_name}/timeline."""

    model_config = ConfigDict(populate_by_name=True)

    vendor_name: str
    window: str
    resolution: str
    region: str
    from_: datetime = Field(
        alias="from",
        serialization_alias="from",
    )
    to: datetime
    current: TimelineCurrent
    points: list[TimelineBucket] = Field(default_factory=list)
