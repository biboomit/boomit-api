from pydantic import BaseModel, Field
from datetime import datetime


class LatestReportResponse(BaseModel):
    report_id: str = Field(..., description="ID único del reporte")
    agent_config_id: str = Field(..., description="ID de la configuración del agente")
    generated_at: str = Field(..., description="Fecha y hora de generación del reporte")
    report_json: dict = Field(..., description="JSON del reporte generado")

    class Config:
        json_schema_extra = {
            "example": {
                "report_id": "7d9f6f24-5e5e-4a4d-8c92-123456789abc",
                "agent_config_id": "agent123",
                "generated_at": "2026-01-15T10:30:00",
                "report_json": {
                    "blocks": [],
                    "metadata": {}
                }
            }
        }
