from fastapi import APIRouter, Query, HTTPException, Depends
from datetime import datetime

from app.core.config import settings
from app.middleware.auth import get_current_user
from app.services.dashboards import DashboardService, dashboard_service
from app.schemas.dashboards import DashboardResponse, DashboardListResponse, DashboardUpdateRequest, DashboardUpdateResponse, DashboardCreateRequest, DashboardCreateResponse

router = APIRouter()


def get_dashboard_service() -> DashboardService:
    return dashboard_service

@router.get("/", response_model=DashboardListResponse)
async def get_dashboards(
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(
        settings.DEFAULT_PER_PAGE,
        ge=1,
        le=settings.MAX_PER_PAGE,
        description="Number of items per page",
    ),
    company_id: str = Query(None, description="Company ID"),
    product_id: str = Query(None, description="Product ID"),
    service: DashboardService = Depends(get_dashboard_service),
    current_user: dict = Depends(get_current_user)
):
    """Get a list of dashboards with pagination.

    Args:
        page (int, optional): Page number. Defaults to Query(1, ge=1, description="Page number").
        per_page (int, optional): Number of items per page. Defaults to Query(settings.DEFAULT_PER_PAGE, ge=1, le=settings.MAX_PER_PAGE, description="Number of items per page").
        company_id (str, optional): Company ID to filter dashboards. Defaults to None.
        product_id (str, optional): Product ID to filter dashboards. Defaults to None.
        service (DashboardService, optional): Dashboard service instance. Defaults to Depends(get_dashboard_service).
    """
    try:
        skip = (page - 1) * per_page
        dashboards, total = await service.get_dashboards(skip=skip, limit=per_page, company_id=company_id, product_id=product_id)

        dashboard_responses = [DashboardResponse(**d.to_dict()) for d in dashboards]

        return DashboardListResponse(
            dashboards=dashboard_responses, total=total, page=page, per_page=per_page
        )
    except Exception as e:
        raise e

@router.get("/{product_id}", response_model=DashboardResponse)
async def get_dashboard_by_product_id(
    product_id: str,
    service: DashboardService = Depends(get_dashboard_service),
    current_user: dict = Depends(get_current_user),
):
    """Obtener un dashboard por product_id.

    Args:
        product_id (str): Identificador del producto asociado al dashboard.
    """
    try:
        dashboard = await service.get_dashboard_by_product_id(product_id=product_id)
        if dashboard is None:
            raise HTTPException(status_code=404, detail=f"No se encontró un dashboard con product_id '{product_id}'.")
        return DashboardResponse(**dashboard.to_dict())
    except HTTPException:
        raise
    except Exception as e:
        raise e


@router.post("/", response_model=DashboardCreateResponse, status_code=201)
async def create_dashboard(
    body: DashboardCreateRequest,
    service: DashboardService = Depends(get_dashboard_service),
    current_user: dict = Depends(get_current_user),
):
    """Crear un nuevo registro de dashboard en DIM_MAESTRO_DASH.

    Args:
        body (DashboardCreateRequest): Datos del nuevo dashboard.
    """
    try:
        rows_affected = await service.create_dashboard(payload=body)
        return DashboardCreateResponse(
            message="Dashboard creado correctamente.",
            dash_id=body.dash_id,
            rows_affected=rows_affected,
        )
    except Exception as e:
        raise e

@router.get("/{product_id}", response_model=DashboardResponse)
async def get_dashboard_by_product_id(
    product_id: str,
    service: DashboardService = Depends(get_dashboard_service),
    current_user: dict = Depends(get_current_user),
):
    """Obtener un dashboard por product_id.

    Args:
        product_id (str): Identificador del producto asociado al dashboard.
    """
    try:
        dashboard = await service.get_dashboard_by_product_id(product_id=product_id)
        if dashboard is None:
            raise HTTPException(status_code=404, detail=f"No se encontró un dashboard con product_id '{product_id}'.")
        return DashboardResponse(**dashboard.to_dict())
    except HTTPException:
        raise
    except Exception as e:
        raise e


@router.post("/", response_model=DashboardCreateResponse, status_code=201)
async def create_dashboard(
    body: DashboardCreateRequest,
    service: DashboardService = Depends(get_dashboard_service),
    current_user: dict = Depends(get_current_user),
):
    """Crear un nuevo registro de dashboard en DIM_MAESTRO_DASH.

    Args:
        body (DashboardCreateRequest): Datos del nuevo dashboard.
    """
    try:
        rows_affected = await service.create_dashboard(payload=body)
        return DashboardCreateResponse(
            message="Dashboard creado correctamente.",
            dash_id=body.dash_id,
            rows_affected=rows_affected,
        )
    except Exception as e:
        raise e


@router.put("/{producto_id}", response_model=DashboardUpdateResponse)
async def update_dashboard(
    producto_id: str,
    body: DashboardUpdateRequest,
    service: DashboardService = Depends(get_dashboard_service),
    current_user: dict = Depends(get_current_user),
):
    """Actualizar url y/o url_embebido de un dashboard por producto_id.

    Args:
        producto_id (str): Identificador del producto asociado al dashboard.
        body (DashboardUpdateRequest): Campos a actualizar (url, url_embebido).
    """
    if body.url is None and body.url_embebido is None:
        raise HTTPException(status_code=422, detail="Debe proporcionar al menos un campo para actualizar: url o url_embebido.")

    try:
        rows_affected = await service.update_dashboard(producto_id=producto_id, payload=body)
        if rows_affected == 0:
            raise HTTPException(status_code=404, detail=f"No se encontró un dashboard con producto_id '{producto_id}'.")
        return DashboardUpdateResponse(
            message="Dashboard actualizado correctamente.",
            producto_id=producto_id,
            rows_affected=rows_affected,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise e
