from fastapi import APIRouter

from app.api.v1.endpoints import health, companies, dashboards

api_router = APIRouter()

api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(companies.router, prefix="/companies", tags=["companies"])
api_router.include_router(dashboards.router, prefix="/dashboards", tags=["dashboards"])
