from fastapi import APIRouter, Depends, HTTPException, status
from app.services.report_generation_service import ReportGenerationService
from app.middleware.auth import get_current_user
from pydantic import BaseModel, Field
from typing import Optional

router = APIRouter()
service = ReportGenerationService()

# TODO: Mover esto a un schema separado
class ReportGenerationRequest(BaseModel):
    agent_id: str = Field(..., description="ID del agente de configuración de reporte")
    # Puedes agregar filtros de fechas u otros parámetros si lo requiere el negocio

# TODO: Generar documentacion de request y response para swagger
@router.post(
    "/generate-report",
    status_code=status.HTTP_201_CREATED,
    summary="Genera un reporte inteligente y lo almacena en BigQuery",
    description="Genera el reporte, lo almacena (JSON y PDF) y responde con el nombre del archivo generado."
)
def generate_report(
    req: ReportGenerationRequest,
    current_user: dict = Depends(get_current_user),
    service: ReportGenerationService = Depends(lambda: service)
):
    user_id = current_user["sub"]
    try:
        file_name = service.generate_report(agent_id=req.agent_id, user_id=user_id)
        return {"pdf_file_name": file_name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
