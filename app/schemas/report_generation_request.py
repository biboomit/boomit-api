from pydantic import BaseModel, Field

class ReportGenerationRequest(BaseModel):
    agent_id: str = Field(..., description="ID del agente de configuración de reporte", example="agente-123")
    dateFrom: str = Field(..., description="Fecha de inicio (YYYY-MM-DD)", example="2025-12-01")
    dateTo: str = Field(..., description="Fecha de fin (YYYY-MM-DD)", example="2025-12-31")
