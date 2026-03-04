from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class DashboardResponse(BaseModel):
    dashboard_id: str = Field(..., description="Identificador único del dashboard")
    empresa_id: str = Field(..., description="Identificador único de la empresa")
    producto_id: str = Field(..., description="Identificador único del producto")
    nombre_dashboard: str = Field(..., description="Nombre del dashboard")
    nombre_empresa: str = Field(..., description="Nombre de la empresa asociada al dashboard")
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
                "empresa_id": "emp123",
                "nombre_dashboard": "Ventas Mensuales",
                "nombre_empresa": "Empresa XYZ",
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

class DashboardCreateRequest(BaseModel):
    dash_id: str = Field(..., description="Identificador único del dashboard")
    producto_id: str = Field(..., description="Identificador único del producto")
    url: str = Field(..., description="URL del dashboard")
    url_embebido: str = Field(..., description="URL embebida del dashboard")
    estado: str = Field("Activo", description="Estado del dashboard (ej: Activo, Inactivo)")

    class Config:
        schema_extra = {
            "example": {
                "dash_id": "db001",
                "producto_id": "prod123",
                "url": "https://example.com/dashboards/db001",
                "url_embebido": "https://example.com/embed/db001",
                "estado": "Activo"
            }
        }


class DashboardCreateResponse(BaseModel):
    message: str
    dash_id: str
    rows_affected: int


class DashboardUpdateRequest(BaseModel):
    url: Optional[str] = Field(None, description="Nueva URL del dashboard")
    url_embebido: Optional[str] = Field(None, description="Nueva URL embebida del dashboard")

    class Config:
        schema_extra = {
            "example": {
                "url": "https://example.com/dashboards/db001",
                "url_embebido": "https://example.com/embed/db001"
            }
        }

class DashboardUpdateResponse(BaseModel):
    message: str
    producto_id: str
    rows_affected: int

class DashboardInternal(BaseModel):
    dashboard_id: str
    empresa_id: str
    producto_id: str
    nombre_dashboard: str
    nombre_empresa: str
    url: str
    embed_url: str
    estado: str
    fecha_creacion: datetime
    fecha_actualizacion: Optional[datetime]
    
    def to_dict(self):
        return {
            "dashboard_id": self.dashboard_id,
            "empresa_id": self.empresa_id,
            "producto_id": self.producto_id,
            "nombre_dashboard": self.nombre_dashboard,
            "nombre_empresa": self.nombre_empresa,
            "url": self.url,
            "embed_url": self.embed_url,
            "estado": self.estado,
            "fecha_creacion": self.fecha_creacion,
            "fecha_actualizacion": self.fecha_actualizacion,
        }
    