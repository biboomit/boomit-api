from fastapi import APIRouter, Query, Depends, HTTPException, Path
from typing import Optional
from datetime import datetime

from app.core.config import settings
from app.services.reviews import ReviewService, review_service
from app.schemas.reviews import (
    ReviewListResponse,
    ReviewSourceListResponse,
    PaginatedReviewsResponse,
    MetricsResponse
)
from app.middleware.auth import get_current_user
from app.core.exceptions import DatabaseConnectionError
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


def get_review_service() -> ReviewService:
    return review_service


@router.get("/sources", response_model=ReviewSourceListResponse)
async def get_review_sources(
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(
        settings.DEFAULT_PER_PAGE,
        ge=1,
        le=settings.MAX_PER_PAGE,
        description="Number of items per page",
    ),
    source: Optional[str] = Query(
        None, description="Filter by source (android/ios)", regex="^(?i)(android|ios)$"
    ),
    has_reviews: Optional[bool] = Query(None, description="Filter apps with reviews"),
    service: ReviewService = Depends(get_review_service),
    current_user: dict = Depends(get_current_user),
):
    """Get a paginated list of review sources (apps) with aggregated metadata.

    This endpoint returns apps with their review statistics including:
    - Total number of reviews
    - Average rating
    - First and last review dates

    Args:
        page: Page number (starts at 1)
        per_page: Number of items per page
        source: Optional filter by source (android/ios)
        has_reviews: Optional filter for apps with/without reviews
        service: Review service dependency
        current_user: Authenticated user dependency

    Returns:
        ReviewSourceListResponse with paginated sources and metadata
    """
    try:
        skip = (page - 1) * per_page
        sources, total = await service.get_review_sources(
            skip=skip, limit=per_page, source=source, has_reviews=has_reviews
        )

        return ReviewSourceListResponse(
            sources=sources, total=total, page=page, per_page=per_page
        )
    except DatabaseConnectionError as e:
        logger.error(f"Database error in get_review_sources: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error in get_review_sources: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/reviews/{app_id}", response_model=PaginatedReviewsResponse)
async def get_reviews_by_app(
    app_id: str = Path(..., description="App ID to fetch reviews for"),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(
        settings.DEFAULT_PER_PAGE,
        ge=1,
        le=settings.MAX_PER_PAGE,
        description="Number of items per page",
    ),
    rating_min: Optional[int] = Query(
        None, ge=1, le=5, description="Minimum rating filter (1-5)"
    ),
    rating_max: Optional[int] = Query(
        None, ge=1, le=5, description="Maximum rating filter (1-5)"
    ),
    date_from: Optional[datetime] = Query(
        None, description="Filter reviews from this date (ISO 8601 format)"
    ),
    date_to: Optional[datetime] = Query(
        None, description="Filter reviews until this date (ISO 8601 format)"
    ),
    service: ReviewService = Depends(get_review_service),
    current_user: dict = Depends(get_current_user),
):
    """Get paginated reviews for a specific app with optional filters.

    This endpoint returns individual reviews for a specific app with support for:
    - Rating range filtering
    - Date range filtering
    - Pagination

    Args:
        app_id: App ID to fetch reviews for
        page: Page number (starts at 1)
        per_page: Number of items per page
        rating_min: Minimum rating (1-5)
        rating_max: Maximum rating (1-5)
        date_from: Start date for filtering reviews
        date_to: End date for filtering reviews
        service: Review service dependency
        current_user: Authenticated user dependency

    Returns:
        PaginatedReviewsResponse with reviews and metadata

    Raises:
        HTTPException: 404 if app_id doesn't exist, 400 for invalid parameters, 500 for server errors
    """
    # Validate rating range
    if rating_min is not None and rating_max is not None and rating_min > rating_max:
        raise HTTPException(
            status_code=400, detail="rating_min cannot be greater than rating_max"
        )

    # Validate date range
    if date_from is not None and date_to is not None and date_from > date_to:
        raise HTTPException(
            status_code=400, detail="date_from cannot be greater than date_to"
        )

    try:
        skip = (page - 1) * per_page
        reviews, total, app_id_result, source = await service.get_reviews_by_app(
            app_id=app_id,
            skip=skip,
            limit=per_page,
            rating_min=rating_min,
            rating_max=rating_max,
            date_from=date_from,
            date_to=date_to,
        )

        return PaginatedReviewsResponse(
            app_id=app_id_result,
            source=source,
            reviews=reviews,
            total=total,
            page=page,
            per_page=per_page,
        )
    except DatabaseConnectionError as e:
        error_message = str(e)
        if "not found" in error_message.lower():
            logger.warning(f"App ID not found: {app_id}")
            raise HTTPException(status_code=404, detail=f"App ID '{app_id}' not found")
        logger.error(f"Database error in get_reviews_by_app: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error in get_reviews_by_app for app {app_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/metrics", response_model=MetricsResponse)
async def get_metrics(
    app_id: str = Query(..., description="App ID to fetch metrics for"),
    date_from: Optional[datetime] = Query(
        None, description="Start date for metrics (ISO 8601 format)"
    ),
    date_to: Optional[datetime] = Query(
        None, description="End date for metrics (ISO 8601 format)"
    ),
    service: ReviewService = Depends(get_review_service),
    current_user: dict = Depends(get_current_user),
):
    """Get metrics for a specific app.
    
    Args:
        app_id: App ID to fetch metrics for
        date_from: Start date for metrics
        date_to: End date for metrics
        service: Review service dependency
        current_user: Authenticated user dependency

    Raises:
        HTTPException: If the app ID is not found or if there is a server error.

    Returns:
        MetricsResponse: The metrics for the specified app.
    """
    
    if date_from is not None and date_to is not None and date_from > date_to:
        raise HTTPException(
            status_code=400, detail="date_from cannot be greater than date_to"
        )
        
    try:
        metrics, time_frame, source = await service.get_metrics(
            app_id=app_id, date_from=date_from, date_to=date_to
        )
        return MetricsResponse(app_id=app_id, metrics=metrics, time_frame=time_frame, source=source)
    except DatabaseConnectionError as e:
        error_message = str(e)
        if "not found" in error_message.lower():
            logger.warning(f"App ID not found for metrics: {app_id}")
            raise HTTPException(status_code=404, detail=f"App ID '{app_id}' not found")
        logger.error(f"Database error in get_metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error in get_metrics for app {app_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/", response_model=ReviewListResponse, deprecated=True)
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

    DEPRECATED: This endpoint groups all reviews which can lead to large response objects.
    Use /review-sources for listing apps and /reviews/{app_id} for individual app reviews.

    Args:
        page: Page number
        per_page: Number of items per page
        app_id: Optional App ID filter
        service: Review service dependency
        current_user: Authenticated user dependency

    Returns:
        ReviewListResponse (deprecated format)
    """
    try:
        skip = (page - 1) * per_page
        review_responses, total = await service.get_reviews(
            skip=skip, limit=per_page, app_id=app_id
        )

        return ReviewListResponse(
            reviews=review_responses, total=total, page=page, per_page=per_page
        )
    except Exception as e:
        logger.error(f"Error in deprecated get_reviews endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))
