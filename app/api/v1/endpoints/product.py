from fastapi import APIRouter, Query, HTTPException, Depends
from datetime import datetime

from app.core.config import settings
from app.services.products import ProductService, product_service
from app.schemas.products import ProductResponse, ProductListResponse
from app.middleware.auth import get_current_user


router = APIRouter()


def get_company_service() -> ProductService:
    return product_service


@router.get("/", response_model=ProductListResponse)
async def get_products(
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(
        settings.DEFAULT_PER_PAGE,
        ge=1,
        le=settings.MAX_PER_PAGE,
        description="Number of items per page",
    ),
    state: str = Query(
        default=settings.DEFAULT_STATE,
        description="Estado del producto",
        regex="^(?i)(active|discontinued|all)$",
    ),
    service: ProductService = Depends(get_company_service),
    current_user: dict = Depends(get_current_user),
):
    """Get a list of products with pagination.

    Args:
        page (int, optional): Page number. Defaults to Query(1, ge=1, description="Page number").
        per_page (int, optional): Number of items per page. Defaults to Query(settings.DEFAULT_PER_PAGE, ge=1, le=settings.MAX_PER_PAGE, description="Number of items per page").
        service (productService, optional): Product service instance. Defaults to Depends(get_company_service).
    """
    try:
        skip = (page - 1) * per_page
        products, total = await service.get_products(skip=skip, limit=per_page, state=state)

        product_responses = [ProductResponse(**c.to_dict()) for c in products]

        return ProductListResponse(
            products=product_responses, total=total, page=page, per_page=per_page
        )
    except Exception as e:
        raise e
