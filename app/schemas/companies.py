from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class CompanyResponse(BaseModel):
    empresa_id: int = Field(..., description="Identificador único de la empresa")
    nombre_empresa: str = Field(..., description="Nombre de la empresa")
    pais: str = Field(..., description="País donde se encuentra la empresa")
    industria: str = Field(..., description="Industria a la que pertenece la empresa")
    fecha_inicio_relacion: datetime = Field(..., description="Fecha de inicio de la relación con la empresa")
    fecha_fin_relacion: Optional[datetime] = Field(None, description="Fecha de fin de la relación con la empresa")
    estado_empresa: str = Field(..., description="Estado actual de la empresa")
    motivo_cierre: Optional[str] = Field(None, description="Motivo del cierre de la empresa, si aplica")
    fecha_creacion: datetime = Field(..., description="Fecha de creación del registro de la empresa")
    fecha_actualizacion: Optional[datetime] = Field(None, description="Fecha de la última actualización del registro de la empresa")
    
    class Config:
        from_attributes = True
        orm_mode = True
        schema_extra = {
            "example": {
                "empresa_id": 1,
                "nombre_empresa": "Tech Solutions",
                "pais": "España",
                "industria": "Tecnología",
                "fecha_inicio_relacion": "2022-01-15T00:00:00",
                "fecha_fin_relacion": None,
                "estado_empresa": "Activa",
                "motivo_cierre": None,
                "fecha_creacion": "2022-01-15T12:34:56",
                "fecha_actualizacion": "2023-03-10T09:21:45"
            }
        }
        
class CompanyListResponse(BaseModel):
    companies: list[CompanyResponse]
    total: int
    page: int
    per_page: int
    
class CompanyInternal(BaseModel):
    empresa_id: int
    nombre_empresa: str
    pais: str
    industria: str
    fecha_inicio_relacion: datetime
    fecha_fin_relacion: Optional[datetime]
    estado_empresa: str
    motivo_cierre: Optional[str]
    fecha_creacion: datetime
    fecha_actualizacion: Optional[datetime]
    
    def to_dict(self):
        return {
            "empresa_id": self.empresa_id,
            "nombre_empresa": self.nombre_empresa,
            "pais": self.pais,
            "industria": self.industria,
            "fecha_inicio_relacion": self.fecha_inicio_relacion,
            "fecha_fin_relacion": self.fecha_fin_relacion,
            "estado_empresa": self.estado_empresa,
            "motivo_cierre": self.motivo_cierre,
            "fecha_creacion": self.fecha_creacion,
            "fecha_actualizacion": self.fecha_actualizacion
        }