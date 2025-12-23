from fastapi import APIRouter

from app.api.v1.endpoints import health, companies, dashboards, campaigns, product, reviews, apps, emerging_themes, websocket, webhooks, batch_triggers, chat, ai_report_agent

api_router = APIRouter()

api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(companies.router, prefix="/companies", tags=["companies"])
api_router.include_router(dashboards.router, prefix="/dashboards", tags=["dashboards"])
api_router.include_router(campaigns.router, prefix="/campaigns", tags=["campaigns"])
api_router.include_router(product.router, prefix="/products", tags=["products"])
api_router.include_router(reviews.router, prefix="/apps", tags=["apps"])
api_router.include_router(apps.router, prefix="/apps", tags=["apps"])
api_router.include_router(emerging_themes.router, prefix="/apps", tags=["apps"])
api_router.include_router(websocket.router, tags=["websocket"])
api_router.include_router(webhooks.router, tags=["webhooks"])
api_router.include_router(batch_triggers.router, tags=["batch proxies"])
api_router.include_router(chat.router, tags=["chat"])
api_router.include_router(ai_report_agent.router, prefix="/reports", tags=["reports"])