from fastapi import APIRouter, Depends, HTTPException, status, Body
from fastapi.responses import HTMLResponse
from app.services.report_generation_service import ReportGenerationService
from app.middleware.auth import get_current_user
from app.schemas.report_generation_request import ReportGenerationRequest
from app.schemas.report_generation_response import ReportGenerationResponse

router = APIRouter()

service = ReportGenerationService()

@router.post(
    "/generate-report",
    status_code=status.HTTP_201_CREATED,
    summary="Genera un reporte inteligente y lo almacena en BigQuery",
    description="Genera el reporte de marketing, lo almacena (JSON). Admite top_n para limitar campañas top.",
    response_description="Confirmación de almacenamiento exitoso",
    response_model=ReportGenerationResponse,
    responses={
        201: {
            "description": "Reporte generado exitosamente",
            "content": {
                "application/json": {
                    "example": {
                        "message": "Successfully generated report structure for agent_id: agent123, user_id: user456",
                        "report_id": "7d9f6f24-5e5e-4a4d-8c92-123456789abc"
                    }
                }
            }
        },
        500: {"description": "Error interno del servidor"}
    }
)
def generate_report(
    req: ReportGenerationRequest = Body(
        ...,
        example={
            "agent_id": "agente-123",
            "dateFrom": "2025-12-01",
            "dateTo": "2025-12-31",
            "top_n": 10,
        },
    ),
    current_user: dict = Depends(get_current_user),
    service: ReportGenerationService = Depends(lambda: service)
):
    """
    Genera un reporte de marketing inteligente usando los datos analíticos filtrados por fechas y top_n.
    - **agent_id**: ID del agente de configuración de reporte
    - **dateFrom**: Fecha de inicio (YYYY-MM-DD)
    - **dateTo**: Fecha de fin (YYYY-MM-DD)
    - **top_n**: Cantidad de campañas top a incluir (ranking por FTD luego inversión, default 10)
    """
    user_id = current_user["sub"]
    try:
        result = service.generate_report(
            agent_id=req.agent_id,
            user_id=user_id,
            date_from=req.dateFrom,
            date_to=req.dateTo,
            top_n=req.top_n,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get(
    "/report/{report_id}/html",
    response_class=HTMLResponse,
    summary="Obtiene el HTML renderizado de un reporte",
    description="Obtiene el HTML renderizado de un reporte generado previamente usando su report_id.",
    response_description="HTML del reporte renderizado",
    responses={
        200: {
            "description": "HTML del reporte",
            "content": {"text/html": {}}
        },
        404: {"description": "Reporte no encontrado"},
        500: {"description": "Error interno del servidor"}
    }
)
def get_report_html(
    report_id: str,
    current_user: dict = Depends(get_current_user),
    service: ReportGenerationService = Depends(lambda: service)
):
    """
    Obtiene el HTML renderizado de un reporte generado previamente.
    - **report_id**: ID del reporte generado
    """
    try:
        html_content = service.get_report_html(report_id)
        return HTMLResponse(content=html_content, media_type="text/html")
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
