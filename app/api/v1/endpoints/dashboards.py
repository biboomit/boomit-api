from fastapi import APIRouter, Query, HTTPException, Depends
from datetime import datetime

from app.core.config import settings
from app.middleware.auth import get_current_user
from app.services.dashboards import DashboardService, dashboard_service
from app.schemas.dashboards import DashboardResponse, DashboardListResponse

router = APIRouter()


def get_dashboard_service() -> DashboardService:
    return dashboard_service

@router.get("/", response_model=DashboardListResponse)
async def get_dashboards(
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(
        settings.DEFAULT_PER_PAGE,
        ge=1,
        le=settings.MAX_PER_PAGE,
        description="Number of items per page",
    ),
    company_id: str = Query(None, description="Company ID"),
    service: DashboardService = Depends(get_dashboard_service),
    current_user: dict = Depends(get_current_user)
):
    """Get a list of dashboards with pagination.

    Args:
        page (int, optional): Page number. Defaults to Query(1, ge=1, description="Page number").
        per_page (int, optional): Number of items per page. Defaults to Query(settings.DEFAULT_PER_PAGE, ge=1, le=settings.MAX_PER_PAGE, description="Number of items per page").
        company_id (str, optional): Company ID to filter dashboards. Defaults to Query(..., description="Company ID").
        service (DashboardService, optional): Dashboard service instance. Defaults to Depends(get_dashboard_service).
    """
    try:
        skip = (page - 1) * per_page
        dashboards, total = await service.get_dashboards(skip=skip, limit=per_page, company_id=company_id)

        dashboard_responses = [DashboardResponse(**d.to_dict()) for d in dashboards]

        return DashboardListResponse(
            dashboards=dashboard_responses, total=total, page=page, per_page=per_page
        )
    except Exception as e:
        raise e