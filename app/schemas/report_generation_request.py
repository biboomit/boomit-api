from pydantic import BaseModel, Field

class ReportGenerationRequest(BaseModel):
    agent_id: str = Field(..., description="ID del agente de configuración de reporte", example="agente-123")
    dateFrom: str = Field(..., description="Fecha de inicio (YYYY-MM-DD)", example="2025-12-01")
    dateTo: str = Field(..., description="Fecha de fin (YYYY-MM-DD)", example="2025-12-31")
    top_n: int = Field(10, ge=1, le=1000, description="Cantidad de campañas top (por FTD luego inversión)", example=10)
