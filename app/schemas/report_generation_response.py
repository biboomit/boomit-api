from pydantic import BaseModel, Field


class ReportGenerationResponse(BaseModel):
    message: str = Field(..., description="Mensaje de confirmación")
    report_id: str = Field(..., description="ID del reporte generado (UUID)")