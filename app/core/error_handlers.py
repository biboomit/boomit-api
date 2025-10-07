from fastapi import Request
from fastapi.responses import JSONResponse
import logging

from app.core.exceptions import AuthError, BoomitAPIException, DatabaseConnectionError
from app.core.config import settings

logger = logging.getLogger(__name__)


async def auth_error_handler(request: Request, exc: AuthError):
    """Handler for authentication errors"""
    logger.warning(
        f"Auth error on {request.url.path}: {exc.message}",
        extra={"details": exc.details},
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.error_code,
            "message": exc.message,
            "details": exc.details,
            "timestamp": exc.timestamp.isoformat(),
        },
    )


async def boomit_exception_handler(request: Request, exc: BoomitAPIException):
    """Handler for custom Boomit exceptions"""
    logger.error(
        f"Boomit exception on {request.url.path}: {exc.message}",
        extra={"details": exc.details},
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.error_code,
            "message": exc.message,
            "details": exc.details,
            "timestamp": exc.timestamp.isoformat(),
        },
    )


async def database_error_handler(request: Request, exc: DatabaseConnectionError):
    """Specific handler for database errors"""
    logger.critical(
        f"Database error on {request.url.path}: {exc.message}",
        extra={"details": exc.details},
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.error_code,
            "message": "Database service temporarily unavailable",
            "details": {} if settings.is_production else exc.details,
            "timestamp": exc.timestamp.isoformat(),
        },
    )


async def general_exception_handler(request: Request, exc: Exception):
    """Handler for unhandled exceptions"""
    logger.error(
        f"Unhandled exception on {request.url.path}: {str(exc)}", exc_info=True
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": "INTERNAL_SERVER_ERROR",
            "message": "An unexpected error occurred",
            "details": {} if settings.is_production else {"error": str(exc)},
            "path": request.url.path,
        },
    )


def register_exception_handlers(app):
    """Registers all exception handlers in the application"""
    app.add_exception_handler(AuthError, auth_error_handler)
    app.add_exception_handler(DatabaseConnectionError, database_error_handler)
    app.add_exception_handler(BoomitAPIException, boomit_exception_handler)
    app.add_exception_handler(Exception, general_exception_handler)
