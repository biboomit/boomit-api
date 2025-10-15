from fastapi import APIRouter, Query, Depends

from app.core.config import settings
from app.services.reviews import ReviewService, review_service
from app.schemas.reviews import ReviewListResponse
from app.middleware.auth import get_current_user

router = APIRouter()


def get_review_service() -> ReviewService:
    return review_service

@router.get("/", response_model=ReviewListResponse)
async def get_reviews(
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(
        settings.DEFAULT_PER_PAGE,
        ge=1,
        le=settings.MAX_PER_PAGE,
        description="Number of items per page",
    ),
    app_id: str = Query(None, description="App ID"),
    service: ReviewService = Depends(get_review_service),
    current_user: dict = Depends(get_current_user),
):
    """Get a list of reviews grouped by app_id and source with pagination.

    Args:
        page (int): The page number for pagination. Must be >= 1.
        per_page (int): Number of items per page. Must be between 1 and the maximum allowed per page.
        app_id (str, optional): The ID of the app to filter reviews by. If None, reviews for all apps are returned.
        service (ReviewService): The review service instance used to fetch reviews.
        current_user (dict): The current authenticated user.

    Returns:
        ReviewListResponse: An object containing the list of reviews, total count, current page, and items per page.
    """
    try:
        skip = (page - 1) * per_page
        review_responses, total = await service.get_reviews(skip=skip, limit=per_page, app_id=app_id)

        return ReviewListResponse(
            reviews=review_responses, total=total, page=page, per_page=per_page
        )
    except Exception as e:
        raise e