from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class DashboardResponse(BaseModel):
    dashboard_id: str = Field(..., description="Identificador único del dashboard")
    nombre_dashboard: str = Field(..., description="Nombre del dashboard")
    url: str = Field(..., description="URL del dashboard")
    embed_url: str = Field(..., description="URL embebida del dashboard")
    estado: str = Field(..., description="Estado actual del dashboard")
    fecha_creacion: datetime = Field(..., description="Fecha de creación del registro del dashboard")
    fecha_actualizacion: Optional[datetime] = Field(None, description="Fecha de la última actualización del registro del dashboard")
    
    class Config:
        from_attributes = True
        orm_mode = True
        schema_extra = {
            "example": {
                "dashboard_id": "db001",
                "nombre_dashboard": "Ventas Mensuales",
                "url": "https://example.com/dashboards/db001",
                "embed_url": "https://example.com/embed/db001",
                "estado": "Activo",
                "fecha_creacion": "2023-01-10T14:30:00",
                "fecha_actualizacion": "2023-03-15T10:20:00"
            }
        }

class DashboardListResponse(BaseModel):
    dashboards: list[DashboardResponse]
    total: int
    page: int
    per_page: int

class DashboardInternal(BaseModel):
    dashboard_id: str
    nombre_dashboard: str
    url: str
    embed_url: str
    estado: str
    fecha_creacion: datetime
    fecha_actualizacion: Optional[datetime]
    
    def to_dict(self):
        return {
            "dashboard_id": self.dashboard_id,
            "nombre_dashboard": self.nombre_dashboard,
            "url": self.url,
            "embed_url": self.embed_url,
            "estado": self.estado,
            "fecha_creacion": self.fecha_creacion,
            "fecha_actualizacion": self.fecha_actualizacion,
        }
    