from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class CampaignResponse(BaseModel):
    campana_id: str = Field(..., description="Identificador único de la campaña")
    network_id: str = Field(..., description="Identificador de la red asociada a la campaña")
    empresa_id: str = Field(..., description="Identificador de la empresa propietaria de la campaña")
    producto_id: str = Field(..., description="Identificador del producto promocionado en la campaña")
    canal_id: str = Field(..., description="Identificador del canal utilizado para la campaña")
    nombre_campana: str = Field(..., description="Nombre de la campaña")
    objetivo_campana: str = Field(..., description="Objetivo principal de la campaña")
    tipo_campana: str = Field(..., description="Tipo de campaña (e.g., CPC, CPM)")
    fecha_primer_inicio: datetime = Field(..., description="Fecha del primer inicio de la campaña")
    fecha_ultimo_apagado: Optional[datetime] = Field(None, description="Fecha del último apagado de la campaña")
    estado_campana: str = Field(..., description="Estado actual de la campaña (e.g., activa, pausada)")
    fecha_creacion: datetime = Field(..., description="Fecha de creación del registro de la campaña")
    fecha_actualizacion: Optional[datetime] = Field(None, description="Fecha de la última actualización del registro de la campaña")
    
    class Config:
        from_attributes = True
        orm_mode = True
        schema_extra = {
            "example": {
                "campana_id": "ca0001",
                "network_id": "nw001",
                "empresa_id": "ee0001",
                "producto_id": "pr0001",
                "canal_id": "ch0001",
                "nombre_campana": "Campaña Primavera 2023",
                "objetivo_campana": "Aumentar ventas",
                "tipo_campana": "CPC",
                "fecha_primer_inicio": "2023-03-01T00:00:00",
                "fecha_ultimo_apagado": None,
                "estado_campana": "Activa",
                "fecha_creacion": "2023-03-01T12:34:56",
                "fecha_actualizacion": "2023-03-10T09:21:45"
            }
        }
        
class CampaignListResponse(BaseModel):
    campaigns: list[CampaignResponse]
    total: int
    page: int
    per_page: int
    
class CampaignInternal(BaseModel):
    campana_id: str
    network_id: str
    empresa_id: str
    producto_id: str
    canal_id: str
    nombre_campana: str
    objetivo_campana: str
    tipo_campana: str
    fecha_primer_inicio: datetime
    fecha_ultimo_apagado: Optional[datetime]
    estado_campana: str
    fecha_creacion: datetime
    fecha_actualizacion: Optional[datetime]
    
    def to_dict(self):
        return {
            "campana_id": self.campana_id,
            "network_id": self.network_id,
            "empresa_id": self.empresa_id,
            "producto_id": self.producto_id,
            "canal_id": self.canal_id,
            "nombre_campana": self.nombre_campana,
            "objetivo_campana": self.objetivo_campana,
            "tipo_campana": self.tipo_campana,
            "fecha_primer_inicio": self.fecha_primer_inicio,
            "fecha_ultimo_apagado": self.fecha_ultimo_apagado,
            "estado_campana": self.estado_campana,
            "fecha_creacion": self.fecha_creacion,
            "fecha_actualizacion": self.fecha_actualizacion
        }