import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from app.core.config import settings
from app.middleware.timing import TimingMiddleware
from app.middleware.logging import LoggingMiddleware
from app.api.v1.router import api_router

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
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
    lifespan=lifespan,
)

# Security middleware
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.get_allowed_hosts())

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_cors_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Response time and logging middleware
app.add_middleware(TimingMiddleware)
app.add_middleware(LoggingMiddleware)

app.include_router(api_router, prefix=settings.API_V1_PREFIX)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.reload_enabled,
        log_level=settings.LOG_LEVEL.lower(),
    )
