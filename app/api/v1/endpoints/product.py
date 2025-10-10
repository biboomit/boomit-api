from fastapi import APIRouter, Query, HTTPException, Depends
from datetime import datetime

from app.core.config import settings
from app.services.products import ProductService, product_service
from app.schemas.products import ProductResponse, ProductListResponse
from app.middleware.auth import get_current_user


router = APIRouter()


def get_product_service() -> ProductService:
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
    company_id: str = Query(None, description="Company ID"),
    service: ProductService = Depends(get_product_service),
    current_user: dict = Depends(get_current_user),
):
    """Get a list of products with pagination.

    Args:
        page (int, optional): Page number. Defaults to Query(1, ge=1, description="Page number").
        per_page (int, optional): Number of items per page. Defaults to Query(settings.DEFAULT_PER_PAGE, ge=1, le=settings.MAX_PER_PAGE, description="Number of items per page").
        state (str, optional): Product state to filter by. Defaults to Query(default=settings.DEFAULT_STATE, description="Estado del producto", regex="^(?i)(active|discontinued|all)$").
        company_id (str, optional): Company ID to filter products. Defaults to None.
        service (ProductService, optional): Product service instance. Defaults to Depends(get_product_service).
    """
    try:
        skip = (page - 1) * per_page
        products, total = await service.get_products(skip=skip, limit=per_page, state=state, company_id=company_id)

        product_responses = [ProductResponse(**c.to_dict()) for c in products]

        return ProductListResponse(
            products=product_responses, total=total, page=page, per_page=per_page
        )
    except Exception as e:
        raise e
