import uuid
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.dependencies import get_current_org
from app.db.session import get_db
from app.modules.checks.schemas import CheckResultResponse
from app.modules.checks.service import CheckService, check_service
from app.modules.organizations.models import Organization

router = APIRouter(prefix="/v1/orgs/{org_id}/checks", tags=["Checks"])


def get_chk_service() -> CheckService:
    return check_service


@router.get("/recent", response_model=list[CheckResultResponse])
async def list_recent_check_results(
    org_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: CheckService = Depends(get_chk_service),
) -> list[CheckResultResponse]:
    return await service.list_results_for_org(db, org_id, limit=limit)
