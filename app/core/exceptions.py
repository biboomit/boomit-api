from datetime import datetime
from typing import Any, Dict, Optional
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class BoomitAPIException(Exception):
    def __init__(
        self,
        message: str,
        status_code: int = 500,
        error_code: str = "INTERNAL_ERROR",
        details: Optional[Dict[str, Any]] = None,
    ):
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        self.details = details or {}
        self.timestamp = datetime.utcnow()
        super().__init__(self.message)


class DatabaseConnectionError(BoomitAPIException):
    def __init__(
        self,
        message: str = "Database connection error",
        details: Optional[Dict[str, Any]] = None,
    ):
        logger.error(f"DatabaseConnectionError: {message}, Details: {details}")
        super().__init__(
            message, status_code=500, error_code="DB_CONNECTION_ERROR", details=details
        )


class AuthError(BoomitAPIException):
    def __init__(
        self,
        message: str = "Authentication error",
        status_code: int = 401,
        details: Optional[Dict[str, Any]] = None,
    ):
        logger.warning(f"AuthError: {message}, Details: {details}")
        super().__init__(
            message, status_code=status_code, error_code="AUTH_ERROR", details=details
        )