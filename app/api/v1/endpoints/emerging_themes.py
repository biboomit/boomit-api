from fastapi import APIRouter, Depends, HTTPException, status
from datetime import datetime
import logging

from app.schemas.emerging_themes import (
    EmergingThemesAnalysisRequest,
    EmergingThemesAnalysisResponse,
)
from app.services.emerging_themes import (
    EmergingThemesService,
    emerging_themes_service,
)
from app.middleware.auth import get_current_user
from app.core.exceptions import DatabaseConnectionError

logger = logging.getLogger(__name__)

router = APIRouter()


def get_emerging_themes_service() -> EmergingThemesService:
    """Dependency to get the emerging themes service instance."""
    return emerging_themes_service


@router.post(
    "/emerging-themes",
    response_model=EmergingThemesAnalysisResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Analyze emerging themes from app reviews",
    description="""
    Analyzes reviews from the last 90 days to identify emerging themes and patterns.
    
    This endpoint initiates an asynchronous analysis using OpenAI Batch API.
    The analysis typically takes 2-6 hours to complete.
    
    **Process:**
    1. Fetches up to 1500 reviews from the last 90 days
    2. Sends them to OpenAI Batch API for pattern analysis
    3. Returns a batch_id to track the analysis progress
    
    **Emerging Themes Criteria:**
    - Frequency >= 3 mentions
    - Beyond standard features OR relevant to app category
    - Technical issues, feature requests, competitive comparisons
    
    **Response:**
    Returns batch information immediately (202 Accepted).
    Use the batch_id to check status later via OpenAI API.
    """,
    responses={
        202: {
            "description": "Analysis initiated successfully",
            "content": {
                "application/json": {
                    "example": {
                        "batch_id": "batch_abc123xyz",
                        "status": "processing",
                        "app_id": "com.example.app",
                        "app_name": "Mi App",
                        "app_category": "Finanzas",
                        "total_reviews_analyzed": 1247,
                        "analysis_period_start": "2025-08-27T00:00:00Z",
                        "analysis_period_end": "2025-11-25T23:59:59Z",
                        "created_at": "2025-11-25T15:30:00Z",
                        "message": "Análisis iniciado. El procesamiento puede tomar entre 2-6 horas.",
                    }
                }
            },
        },
        400: {"description": "Invalid request or no reviews found"},
        404: {"description": "App not found"},
        500: {"description": "Internal server error"},
    },
    tags=["Emerging Themes Analysis"],
)
async def analyze_emerging_themes(
    request: EmergingThemesAnalysisRequest,
    service: EmergingThemesService = Depends(get_emerging_themes_service),
    current_user: dict = Depends(get_current_user),
):
    """
    Initiate emerging themes analysis for an app.

    Args:
        request: Request body containing app_id
        service: Injected emerging themes service
        current_user: Authenticated user from JWT token

    Returns:
        EmergingThemesAnalysisResponse with batch_id and metadata

    Raises:
        HTTPException 404: If app not found
        HTTPException 400: If no reviews found in last 90 days
        HTTPException 500: If database or OpenAI API error occurs
    """
    try:
        logger.info(
            f"User {current_user.get('sub', 'unknown')} requested emerging themes "
            f"analysis for app: {request.app_id}"
        )

        # Initiate analysis
        batch, metadata = await service.analyze_emerging_themes(request.app_id)

        # Build response
        response = EmergingThemesAnalysisResponse(
            batch_id=batch.id,
            status="processing",
            app_id=metadata["app_id"],
            app_name=metadata["app_name"],
            app_category=metadata["app_category"],
            total_reviews_analyzed=metadata["total_reviews"],
            analysis_period_start=metadata["start_date"],
            analysis_period_end=metadata["end_date"],
            created_at=datetime.utcnow(),
            message=(
                f"Análisis iniciado exitosamente. Se están procesando "
                f"{metadata['total_reviews']} reviews. "
                f"El procesamiento puede tomar entre 2-6 horas. "
                f"Use el batch_id '{batch.id}' para consultar el estado."
            ),
        )

        logger.info(
            f"Emerging themes analysis initiated successfully. "
            f"Batch ID: {batch.id}, App: {request.app_id}"
        )

        return response

    except ValueError as e:
        # App not found or no reviews
        error_message = str(e)
        logger.warning(f"Validation error for app {request.app_id}: {error_message}")

        if "not found" in error_message.lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"App with ID '{request.app_id}' not found in the system.",
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_message,
            )

    except DatabaseConnectionError as e:
        logger.error(
            f"Database error while analyzing app {request.app_id}: {str(e)}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to connect to database. Please try again later.",
        )

    except Exception as e:
        logger.error(
            f"Unexpected error analyzing emerging themes for app {request.app_id}: {str(e)}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred. Please contact support.",
        )
