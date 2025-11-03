from fastapi import APIRouter, Depends, HTTPException, Path

from app.services.apps import AppService, app_service
from app.schemas.apps import AppDetailsResponse
from app.middleware.auth import get_current_user
from app.core.exceptions import DatabaseConnectionError
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


def get_app_service() -> AppService:
    return app_service


@router.get("/{app_id}", response_model=AppDetailsResponse)
async def get_app_details(
    app_id: str = Path(..., description="App ID to fetch details for"),
    service: AppService = Depends(get_app_service),
    current_user: dict = Depends(get_current_user),
):
    """Get detailed information for a specific app by its ID.

    This endpoint retrieves complete app information from DIM_MAESTRO_REVIEWS
    combined with rating data from DIM_REVIEWS_HISTORICO.

    Args:
        app_id: Unique app identifier (e.g., 'com.farmatodo.app')
        service: App service dependency
        current_user: Authenticated user dependency

    Returns:
        AppDetailsResponse with app details including:
        - Basic app information (name, developer, category, etc.)
        - Download statistics
        - Average rating and total ratings from reviews
        - App store metadata

    Raises:
        HTTPException: 404 if app not found, 500 for server errors

    Example:
        GET /api/v1/apps/com.farmatodo.app
        
        Response:
        {
            "appId": "com.farmatodo.app",
            "appName": "Farmatodo",
            "store": "android",
            "developer": "Farmatodo Inc.",
            "ratingAverage": 4.2,
            "totalRatings": 12543,
            "downloads": 2100000,
            "lastUpdate": "2024-08-10",
            "iconUrl": "https://play-lh.googleusercontent.com/...",
            "category": "Health & Fitness"
        }
    """
    if not app_id.strip():
        raise HTTPException(
            status_code=400, 
            detail="app_id cannot be empty"
        )

    try:
        app_details = await service.get_app_details(app_id.strip())
        
        if not app_details:
            logger.warning(f"App not found: {app_id}")
            raise HTTPException(
                status_code=404, 
                detail=f"App with ID '{app_id}' not found"
            )

        logger.info(f"App details retrieved successfully: {app_id}")
        return app_details

    except HTTPException:
        raise
    except DatabaseConnectionError as e:
        logger.error(f"Database error in get_app_details: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error in get_app_details for {app_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")