from fastapi import APIRouter, Depends, HTTPException, status
from app.services.report_generation_service import ReportGenerationService
from app.middleware.auth import get_current_user
from app.schemas.report_generation_request import ReportGenerationRequest

router = APIRouter()

service = ReportGenerationService()

@router.post(
    "/generate-report",
    status_code=status.HTTP_201_CREATED,
    summary="Genera un reporte inteligente y lo almacena en BigQuery",
    description="Genera el reporte de marketing, lo almacena (JSON) y responde con el nombre del archivo generado.",
    response_description="Confirmación de almacenamiento exitoso",
    response_model=dict,
    responses={
        201: {
            "description": "Reporte generado exitosamente",
            "content": {
                "application/json": {
                    "example": {"message": "Successfully generated report structure for agent_id: agent123, user_id: user456"}
                }
            }
        },
        500: {"description": "Error interno del servidor"}
    }
)
def generate_report(
    req: ReportGenerationRequest = ...,
    current_user: dict = Depends(get_current_user),
    service: ReportGenerationService = Depends(lambda: service)
):
    """
    Genera un reporte de marketing inteligente usando los datos analíticos filtrados por fechas.
    - **agent_id**: ID del agente de configuración de reporte
    - **dateFrom**: Fecha de inicio (YYYY-MM-DD)
    - **dateTo**: Fecha de fin (YYYY-MM-DD)
    """
    user_id = current_user["sub"]
    try:
        result = service.generate_report(
            agent_id=req.agent_id,
            user_id=user_id,
            date_from=req.dateFrom,
            date_to=req.dateTo
        )
        return {"message": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
