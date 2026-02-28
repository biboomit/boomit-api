from fastapi import APIRouter, Query, HTTPException, Depends, status
from datetime import datetime

from app.core.config import settings
from app.services.products import ProductService, product_service
from app.schemas.products import (
    ProductResponse, 
    ProductListResponse, 
    ProductCreateRequest, 
    ProductUpdateRequest
)
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


@router.get("/{product_id}", response_model=ProductResponse)
async def get_product(
    product_id: str,
    service: ProductService = Depends(get_product_service),
    current_user: dict = Depends(get_current_user)
):
    """Get a product by ID.

    Args:
        product_id (str): Product ID to retrieve
        service (ProductService): Product service instance
        current_user (dict): Current authenticated user

    Returns:
        ProductResponse: Product details

    Raises:
        HTTPException: 404 if product not found
    """
    try:
        product = await service.get_product_by_id(product_id)
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product with ID {product_id} not found"
            )
        return ProductResponse(**product.to_dict())
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
async def create_product(
    product_data: ProductCreateRequest,
    service: ProductService = Depends(get_product_service),
    current_user: dict = Depends(get_current_user)
):
    """Create a new product.

    Args:
        product_data (ProductCreateRequest): Product data to create
        service (ProductService): Product service instance
        current_user (dict): Current authenticated user

    Returns:
        ProductResponse: Created product details

    Raises:
        HTTPException: 500 if creation fails
    """
    try:
        product = await service.create_product(product_data)
        return ProductResponse(**product.to_dict())
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create product: {str(e)}"
        )


@router.put("/{product_id}", response_model=ProductResponse)
async def update_product(
    product_id: str,
    product_data: ProductUpdateRequest,
    service: ProductService = Depends(get_product_service),
    current_user: dict = Depends(get_current_user)
):
    """Update an existing product.

    Args:
        product_id (str): Product ID to update
        product_data (ProductUpdateRequest): Product data to update
        service (ProductService): Product service instance
        current_user (dict): Current authenticated user

    Returns:
        ProductResponse: Updated product details

    Raises:
        HTTPException: 404 if product not found, 500 if update fails
    """
    try:
        product = await service.update_product(product_id, product_data)
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product with ID {product_id} not found"
            )
        return ProductResponse(**product.to_dict())
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update product: {str(e)}"
        )
