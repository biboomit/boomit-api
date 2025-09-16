from fastapi import APIRouter, Query, HTTPException, Depends
from datetime import datetime

from app.core.config import settings
from app.services.companies import CompanyService, company_service
from app.schemas.companies import CompanyResponse, CompanyListResponse


router = APIRouter()

def get_company_service() -> CompanyService:
    return company_service

@router.get("/", response_model=CompanyListResponse)
async def get_companies(
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(settings.DEFAULT_PER_PAGE, ge=1, le=settings.MAX_PER_PAGE, description="Number of items per page"),
    service: CompanyService = Depends(get_company_service)
):
    """Get a list of companies with pagination.

    Args:
        page (int, optional): Page number. Defaults to Query(1, ge=1, description="Page number").
        per_page (int, optional): Number of items per page. Defaults to Query(settings.DEFAULT_PER_PAGE, ge=1, le=settings.MAX_PER_PAGE, description="Number of items per page").
        service (CompanyService, optional): Company service instance. Defaults to Depends(get_company_service).
    """
    skip = (page - 1) * per_page
    companies, total = await service.get_companies(skip=skip, limit=per_page)
    
    company_responses = [CompanyResponse(**c.to_dict()) for c in companies]

    return CompanyListResponse(
        companies=company_responses,
        total=total,
        page=page,
        per_page=per_page
    )
