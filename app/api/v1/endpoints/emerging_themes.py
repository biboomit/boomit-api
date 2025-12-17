from fastapi import APIRouter, Depends, HTTPException, status
from datetime import datetime
import logging

from app.schemas.emerging_themes import (
    EmergingThemesAnalysisRequest,
    EmergingThemesAnalysisResponse,
    EmergingThemesResult,
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
    summary="Request AI Analysis of emerging themes from app reviews",
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
    }
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
            f"analysis for app: {request.app_id} (force_new: {request.force_new_analysis})"
        )

        # Initiate analysis (with cache check unless forced)
        batch, metadata = await service.analyze_emerging_themes(
            request.app_id, 
            force_new_analysis=request.force_new_analysis
        )

        # Check if response is from cache
        if metadata.get("from_cache"):
            # Cached response
            response = EmergingThemesAnalysisResponse(
                batch_id=metadata["batch_id"],
                status="completed",  # Cached results are already completed
                app_id=metadata["app_id"],
                total_reviews_analyzed=metadata["total_reviews"],
                analysis_period_start=metadata["start_date"],
                analysis_period_end=metadata["end_date"],
                created_at=metadata["created_at"],
                from_cache=True,
                cache_age_hours=metadata["cache_age_hours"],
                message=(
                    f"Análisis encontrado en caché (edad: {metadata['cache_age_hours']:.1f} horas). "
                    f"Batch ID: '{metadata['batch_id']}'. "
                    f"Use GET /emerging-themes/{request.app_id}/latest para ver los resultados. "
                    f"Para forzar un nuevo análisis, use force_new_analysis=true."
                ),
            )
            
            logger.info(
                f"Returned cached analysis for {request.app_id}. "
                f"Batch ID: {metadata['batch_id']}, Age: {metadata['cache_age_hours']:.1f}h"
            )
        else:
            # New batch created
            response = EmergingThemesAnalysisResponse(
                batch_id=batch.id,
                status="processing",
                app_id=metadata["app_id"],
                total_reviews_analyzed=metadata["total_reviews"],
                analysis_period_start=metadata["start_date"],
                analysis_period_end=metadata["end_date"],
                created_at=datetime.utcnow(),
                from_cache=False,
                cache_age_hours=0.0,
                message=(
                    f"Análisis iniciado exitosamente. Se están procesando "
                    f"{metadata['total_reviews']} reviews. "
                    f"El procesamiento puede tomar entre 2-6 horas. "
                    f"Use el batch_id '{batch.id}' para consultar el estado."
                ),
            )
            
            logger.info(
                f"New emerging themes analysis initiated. "
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

@router.post(
    "/emerging-themes/global",
    summary="Request synchronous global AI analysis of emerging themes from app reviews",
    description="""
    Analiza reviews de los últimos 90 días para identificar temas emergentes y patrones usando un solo prompt global.
    El análisis es síncrono.
    """,
    status_code=status.HTTP_200_OK,
)
async def analyze_emerging_themes_global(
    request: EmergingThemesAnalysisRequest,
    service: EmergingThemesService = Depends(get_emerging_themes_service),
    current_user: dict = Depends(get_current_user),
):
    """
    Inicia el análisis global de temas emergentes para una app y devuelve el resultado directo (prompt único, síncrono).
    """
    try:
        logger.info(
            f"User {current_user.get('sub', 'unknown')} requested synchronous emerging themes "
            f"analysis for app: {request.app_id} (force_new: {request.force_new_analysis})"
        )
        result = await service.analyze_emerging_themes_global(
            request.app_id,
            force_new_analysis=request.force_new_analysis
        )
         # Check if response is from cache
        if result.get("from_cache"):
            # Cached response
            response = EmergingThemesAnalysisResponse(
                batch_id="",  
                status="completed",  # Cached results are already completed
                app_id=result["app_id"],
                total_reviews_analyzed=result["total_reviews"],
                analysis_period_start=result["start_date"],
                analysis_period_end=result["end_date"],
                created_at=result["created_at"],
                from_cache=True,
                cache_age_hours=result["cache_age_hours"],
                message=(
                    f"Análisis encontrado en caché (edad: {result['cache_age_hours']:.1f} horas). "
                    f"App ID: '{result['app_id']}'. "
                    f"Use GET /emerging-themes/{request.app_id}/latest para ver los resultados. "
                    f"Para forzar un nuevo análisis, use force_new_analysis=true."
                ),
            )
            logger.info(
                f"Returned cached analysis for {request.app_id}. "
            )
            return response
        else:
            return result
    except ValueError as e:
        error_message = str(e)
        logger.warning(f"Validation error for app {request.app_id}: {error_message}")
        if "not found" in error_message.lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="App not found"
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_message
            )
    except DatabaseConnectionError as e:
        logger.error(
            f"Database error while analyzing app {request.app_id}: {str(e)}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to connect to database. Please try again later."
        )
    except Exception as e:
        logger.error(
            f"Unexpected error analyzing emerging themes for app {request.app_id}: {str(e)}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred. Please contact support."
        )

@router.get(
    "/emerging-themes/{app_id}/latest",
    response_model=EmergingThemesResult,
    summary="Get latest emerging themes ai analysis",
    description="""
    Retrieves the most recent completed emerging themes ai analysis for an app.
    
    **Use this endpoint to:**
    - Check if analysis has completed (after receiving batch_id from POST endpoint)
    - Get cached results without triggering new analysis
    - View historical analysis results
    
    **Returns:**
    - 200: Analysis completed with themes
    - 404: No analysis found or app doesn't exist
    - 202: Analysis in progress (not yet completed)
    """,
    responses={
        200: {
            "description": "Analysis completed successfully",
            "content": {
                "application/json": {
                    "example": {
                        "app_id": "com.example.app",
                        "app_name": "Mi App",
                        "app_category": "Finanzas",
                        "total_reviews_analyzed": 1247,
                        "analysis_period_start": "2025-08-27T00:00:00Z",
                        "analysis_period_end": "2025-11-25T23:59:59Z",
                        "themes": [
                            {
                                "tema": "Rechazo de tarjetas de débito",
                                "relevancia": "Alto",
                                "indicacion": "Usuarios reportan rechazos frecuentes",
                                "frecuencia": 47
                            }
                        ],
                        "analyzed_at": "2025-11-25T18:30:00Z"
                    }
                }
            },
        },
        202: {"description": "Analysis still processing"},
        404: {"description": "No analysis found for this app"},
    }
)
async def get_latest_emerging_themes(
    app_id: str,
    service: EmergingThemesService = Depends(get_emerging_themes_service),
    current_user: dict = Depends(get_current_user),
):
    """
    Get the latest completed emerging themes analysis for an app.

    Args:
        app_id: Application ID
        service: Injected emerging themes service
        current_user: Authenticated user from JWT token

    Returns:
        EmergingThemesResult with themes and metadata

    Raises:
        HTTPException 404: If no analysis found
        HTTPException 202: If analysis is still processing
        HTTPException 500: If database error occurs
    """
    try:
        logger.info(
            f"User {current_user.get('sub', 'unknown')} requested latest analysis "
            f"for app: {app_id}"
        )

        result = await service.get_latest_completed_analysis(app_id)

        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No emerging themes analysis found for app '{app_id}'",
            )

        # Check if we only have batch info (still processing)
        if result.get("status") == "processing":
            raise HTTPException(
                status_code=status.HTTP_202_ACCEPTED,
                detail={
                    "message": "Analysis is still processing",
                    "batch_id": result.get("batch_id"),
                    "estimated_time": "2-6 hours from creation"
                },
            )

        logger.info(f"Returning completed analysis for app {app_id}")
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Error retrieving analysis for app {app_id}: {str(e)}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve analysis. Please try again later.",
        )