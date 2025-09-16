import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class LoggingMiddleware(BaseHTTPMiddleware):
    """Middleware para logging de peticiones HTTP"""
    
    async def dispatch(self, request: Request, call_next):
        # Log de la petición entrante
        logger.info(f"Petition: {request.method} {request.url}")
        
        response = await call_next(request)
        
        # Log de la respuesta
        logger.info(f"Response: {response.status_code}")
        
        return response