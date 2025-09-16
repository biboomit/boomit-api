"""
Boomit AI Marketing Platform API
FastAPI application main entry point
"""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from app.config import settings

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events"""
    # Startup
    logger.info("Starting up Boomit API...")
    logger.info(f"Environment: {settings.ENVIRONMENT}")
    logger.info(f"Debug mode: {settings.DEBUG}")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Boomit API...")


# Create FastAPI application
app = FastAPI(
    title=settings.APP_NAME,
    description="API para la plataforma de marketing digital Boomit AI que soporta funcionalidades de Reportes y Optimización.",
    version=settings.VERSION,
    docs_url=settings.DOCS_URL if settings.docs_enabled else None,
    redoc_url=settings.REDOC_URL if settings.docs_enabled else None,
    openapi_url=settings.OPENAPI_URL if settings.docs_enabled else None,
    lifespan=lifespan
)

# Security middleware
app.add_middleware(
    TrustedHostMiddleware, 
    allowed_hosts=settings.get_allowed_hosts()
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_cors_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Root endpoint
@app.get("/")
async def root():
    """API root endpoint"""
    return {
        "message": "Boomit AI Marketing Platform API",
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
        "status": "running"
    }

# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring"""
    return {
        "status": "healthy",
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
        "timestamp": "2024-01-01T00:00:00Z"
    }

# API Info endpoint
@app.get("/info")
async def api_info():
    """API information endpoint"""
    return {
        "name": settings.APP_NAME,
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
        "docs_url": f"http://localhost:{settings.PORT}/docs" if settings.docs_enabled else None,
        "openapi_url": f"http://localhost:{settings.PORT}/openapi.json" if settings.docs_enabled else None
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.reload_enabled,
        log_level=settings.LOG_LEVEL.lower()
    )