from fastapi import APIRouter, Query, HTTPException, Depends
from datetime import datetime

from app.core.config import settings
from app.services.campaigns import CampaignService, campaign_service
from app.schemas.campaigns import CampaignResponse, CampaignListResponse
from app.middleware.auth import get_current_user


router = APIRouter()


def get_campaign_service() -> CampaignService:
    return campaign_service


@router.get("/", response_model=CampaignListResponse)
async def get_campaigns(
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(
        settings.DEFAULT_PER_PAGE,
        ge=1,
        le=settings.MAX_PER_PAGE,
        description="Number of items per page",
    ),
    state: str = Query(
        default=settings.DEFAULT_STATE,
        description="Estado de la campaña",
        regex="^(?i)(active|paused|all)$",
    ),
    service: CampaignService = Depends(get_campaign_service),
    current_user: dict = Depends(get_current_user),
):
    """Get a list of campaigns with pagination.

    Args:
        page (int, optional): Page number. Defaults to Query(1, ge=1, description="Page number").
        per_page (int, optional): Number of items per page. Defaults to Query(settings.DEFAULT_PER_PAGE, ge=1, le=settings.MAX_PER_PAGE, description="Number of items per page").
        state (str, optional): Campaign state filter. Defaults to Query(default=settings.DEFAULT_STATE, description="Estado de la campaña", regex="^(active|paused|all)$").
        service (CampaignService, optional): Campaign service instance. Defaults to Depends(get_campaign_service).
    """
    try:
        skip = (page - 1) * per_page
        campaigns, total = await service.get_campaigns(skip=skip, limit=per_page, state=state)

        campaign_responses = [CampaignResponse(**c.to_dict()) for c in campaigns]

        return CampaignListResponse(
            campaigns=campaign_responses, total=total, page=page, per_page=per_page
        )
    except Exception as e:
        raise e
