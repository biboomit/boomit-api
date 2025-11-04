from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional

from app.services.apps import AppService, app_service
from app.schemas.apps import AppSearchResponse, AppDetailsResponse
from app.middleware.auth import get_current_user
from app.core.exceptions import DatabaseConnectionError
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


def get_app_service() -> AppService:
    return app_service


@router.get("/search", response_model=AppSearchResponse)
async def search_apps(
    appName: str = Query(..., description="Name of the app to search for (partial matching supported)"),
    store: Optional[str] = Query(
        None, 
        description="App store filter: 'android' or 'ios'",
        regex="^(?i)(android|ios)$"
    ),
    country: Optional[str] = Query(
        None, 
        description="Country code filter (ISO 2-letter format, e.g., 'US', 'VE')",
        regex="^[A-Z]{2}$"
    ),
    service: AppService = Depends(get_app_service),
    current_user: dict = Depends(get_current_user),
):
    """Search for apps by name with optional filters.

    This endpoint searches through DIM_MAESTRO_REVIEWS for apps whose names
    contain the specified search term, with optional filtering by store and country.
    
    Rating information is retrieved from DIM_REVIEWS_HISTORICO for each app.

    Args:
        appName: Name or partial name of the app to search for (required)
        store: Optional filter by app store ('android' or 'ios')
        country: Optional filter by country code (ISO 2-letter format)
        service: App service dependency
        current_user: Authenticated user dependency

    Returns:
        AppSearchResponse containing an array of matching apps with complete information:
        - Basic app metadata (name, developer, category, etc.)
        - Download statistics  
        - Average rating and total ratings from reviews
        - App store information

    Raises:
        HTTPException: 400 for invalid parameters, 500 for server errors

    Examples:
        GET /api/v1/apps/search?appName=farmatodo
        GET /api/v1/apps/search?appName=banco&store=android
        GET /api/v1/apps/search?appName=delivery&store=android&country=VE
        
        Response:
        {
            "apps": [
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
            ]
        }
    """
    
    # Validar parámetros de entrada
    if not appName or not appName.strip():
        raise HTTPException(
            status_code=400, 
            detail="appName parameter cannot be empty"
        )
    
    # Normalizar store si se proporciona
    if store:
        store = store.lower()
    
    try:
        logger.info(f"Searching apps with name: '{appName}', store: {store}, country: {country}")
        
        # Buscar aplicaciones
        apps = await service.search_apps(
            app_name=appName.strip(),
            store=store,
            country=country
        )

        logger.info(f"Search completed for '{appName}' - found {len(apps)} apps")

        # Retornar respuesta con array de apps
        return AppSearchResponse(apps=apps)

    except DatabaseConnectionError as e:
        logger.error(f"Database error in search_apps: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error in search_apps for '{appName}': {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{app_id}", response_model=AppDetailsResponse)
async def get_app_details(
    app_id: str,
    service: AppService = Depends(get_app_service),
    current_user: dict = Depends(get_current_user),
):
    """Get detailed information for a specific app by ID.

    This endpoint retrieves complete information for a single app from DIM_MAESTRO_REVIEWS
    including ratings data from DIM_REVIEWS_HISTORICO.

    Args:
        app_id: Unique identifier of the app to retrieve
        service: App service dependency
        current_user: Authenticated user dependency

    Returns:
        AppDetailsResponse containing complete app information including ratings

    Raises:
        HTTPException: 404 if app not found, 400 for invalid app_id, 500 for server errors

    Examples:
        GET /api/v1/apps/123456789
        
        Response:
        {
            "appId": "123456789",
            "appName": "Farmatodo",
            "store": "android",
            "developer": "Farmatodo Inc.",
            "ratingAverage": 4.2,
            "totalRatings": 12543,
            "downloads": 2100000,
            "lastUpdate": "2024-08-10",
            "iconUrl": "https://play-lh.googleusercontent.com/...",
            "category": "Health & Fitness", 
        }
    """
    
    # Validar que app_id no esté vacío
    if not app_id or not app_id.strip():
        raise HTTPException(
            status_code=400,
            detail="app_id cannot be empty"
        )
    
    try:
        logger.info(f"Getting details for app: {app_id}")
        
        # Obtener detalles de la aplicación
        app_details = await service.get_app_details(app_id.strip())
        
        if not app_details:
            logger.warning(f"App not found: {app_id}")
            raise HTTPException(
                status_code=404,
                detail=f"App with ID '{app_id}' not found"
            )
        
        logger.info(f"Successfully retrieved details for app: {app_id}")
        return app_details
        
    except HTTPException:
        # Re-raise HTTP exceptions (like 404)
        raise
    except DatabaseConnectionError as e:
        logger.error(f"Database error getting app details for {app_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error getting app details for {app_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")