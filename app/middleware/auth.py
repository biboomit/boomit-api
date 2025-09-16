from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Por ahora, solo pasa la request sin autenticación
        response = await call_next(request)
        return response
