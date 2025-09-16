from fastapi import APIRouter
from datetime import datetime

from app.core.config import settings

# from ....core.config import settings

router = APIRouter()


@router.get("/")
async def root():
    """API root endpoint"""
    return {
        "message": "Boomit AI Marketing Platform API",
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
        "status": "running",
    }


@router.get("/check")
async def health_check():
    return {
        "status": "ok",
        "message": "API functioning correctly",
        "timestamp": datetime.now().isoformat(),
    }


@router.get("/info")
async def api_info():
    """API information endpoint"""
    return {
        "name": settings.APP_NAME,
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
        "docs_url": (
            f"http://localhost:{settings.PORT}/docs" if settings.docs_enabled else None
        ),
        "openapi_url": (
            f"http://localhost:{settings.PORT}/openapi.json"
            if settings.docs_enabled
            else None
        ),
    }
