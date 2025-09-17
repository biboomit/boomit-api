from fastapi import APIRouter

from app.api.v1.endpoints import health, companies

api_router = APIRouter()

api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(companies.router, prefix="/companies", tags=["companies"])
