from fastapi import APIRouter, Query, HTTPException, Depends, status
from datetime import datetime

from app.core.config import settings
from app.services.companies import CompanyService, company_service
from app.schemas.companies import (
    CompanyResponse, 
    CompanyListResponse, 
    CompanyCreateRequest, 
    CompanyUpdateRequest
)
from app.middleware.auth import get_current_user


router = APIRouter()


def get_company_service() -> CompanyService:
    return company_service


@router.get("/", response_model=CompanyListResponse)
async def get_companies(
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(
        settings.DEFAULT_PER_PAGE,
        ge=1,
        le=settings.MAX_PER_PAGE,
        description="Number of items per page",
    ),
    service: CompanyService = Depends(get_company_service),
    current_user: dict = Depends(get_current_user)
):
    """Get a list of companies with pagination.

    Args:
        page (int, optional): Page number. Defaults to Query(1, ge=1, description="Page number").
        per_page (int, optional): Number of items per page. Defaults to Query(settings.DEFAULT_PER_PAGE, ge=1, le=settings.MAX_PER_PAGE, description="Number of items per page").
        service (CompanyService, optional): Company service instance. Defaults to Depends(get_company_service).
    """
    try:
        skip = (page - 1) * per_page
        companies, total = await service.get_companies(skip=skip, limit=per_page)

        company_responses = [CompanyResponse(**c.to_dict()) for c in companies]

        return CompanyListResponse(
            companies=company_responses, total=total, page=page, per_page=per_page
        )
    except Exception as e:
        raise e


@router.get("/{empresa_id}", response_model=CompanyResponse)
async def get_company(
    empresa_id: str,
    service: CompanyService = Depends(get_company_service),
    current_user: dict = Depends(get_current_user)
):
    """Get a company by ID.

    Args:
        empresa_id (str): Company ID to retrieve
        service (CompanyService): Company service instance
        current_user (dict): Current authenticated user

    Returns:
        CompanyResponse: Company details

    Raises:
        HTTPException: 404 if company not found
    """
    try:
        company = await service.get_company_by_id(empresa_id)
        if not company:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Company with ID {empresa_id} not found"
            )
        return CompanyResponse(**company.to_dict())
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/", response_model=CompanyResponse, status_code=status.HTTP_201_CREATED)
async def create_company(
    company_data: CompanyCreateRequest,
    service: CompanyService = Depends(get_company_service),
    current_user: dict = Depends(get_current_user)
):
    """Create a new company.

    Args:
        company_data (CompanyCreateRequest): Company data to create
        service (CompanyService): Company service instance
        current_user (dict): Current authenticated user

    Returns:
        CompanyResponse: Created company details

    Raises:
        HTTPException: 500 if creation fails
    """
    try:
        company = await service.create_company(company_data)
        return CompanyResponse(**company.to_dict())
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create company: {str(e)}"
        )


@router.put("/{empresa_id}", response_model=CompanyResponse)
async def update_company(
    empresa_id: str,
    company_data: CompanyUpdateRequest,
    service: CompanyService = Depends(get_company_service),
    current_user: dict = Depends(get_current_user)
):
    """Update an existing company.

    Args:
        empresa_id (str): Company ID to update
        company_data (CompanyUpdateRequest): Company data to update
        service (CompanyService): Company service instance
        current_user (dict): Current authenticated user

    Returns:
        CompanyResponse: Updated company details

    Raises:
        HTTPException: 404 if company not found, 500 if update fails
    """
    try:
        company = await service.update_company(empresa_id, company_data)
        if not company:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Company with ID {empresa_id} not found"
            )
        return CompanyResponse(**company.to_dict())
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update company: {str(e)}"
        )
