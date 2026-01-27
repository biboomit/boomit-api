from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class ProductCreateRequest(BaseModel):
    empresa_id: str = Field(..., description="Identificador de la empresa propietaria del producto", min_length=1)
    nombre_producto: str = Field(..., description="Nombre del producto", min_length=1, max_length=255)
    categoria_producto: str = Field(..., description="Categoría a la que pertenece el producto", min_length=1, max_length=100)
    estado_producto: str = Field("ACTIVO", description="Estado actual del producto (e.g., ACTIVO, DESCONTINUADO)")
    fecha_lanzamiento: datetime = Field(..., description="Fecha de lanzamiento del producto")
    fecha_fin: Optional[datetime] = Field(None, description="Fecha de fin de vida del producto, si aplica")
    
    class Config:
        schema_extra = {
            "example": {
                "empresa_id": "ee0001",
                "nombre_producto": "Producto A",
                "categoria_producto": "Electrónica",
                "estado_producto": "ACTIVO",
                "fecha_lanzamiento": "2023-01-15T00:00:00",
                "fecha_fin": None
            }
        }

class ProductUpdateRequest(BaseModel):
    empresa_id: Optional[str] = Field(None, description="Identificador de la empresa propietaria del producto", min_length=1)
    nombre_producto: Optional[str] = Field(None, description="Nombre del producto", min_length=1, max_length=255)
    categoria_producto: Optional[str] = Field(None, description="Categoría a la que pertenece el producto", min_length=1, max_length=100)
    estado_producto: Optional[str] = Field(None, description="Estado actual del producto (e.g., ACTIVO, DESCONTINUADO)")
    fecha_lanzamiento: Optional[datetime] = Field(None, description="Fecha de lanzamiento del producto")
    fecha_fin: Optional[datetime] = Field(None, description="Fecha de fin de vida del producto, si aplica")
    
    class Config:
        schema_extra = {
            "example": {
                "estado_producto": "DESCONTINUADO",
                "fecha_fin": "2025-12-31T00:00:00"
            }
        }

class ProductResponse(BaseModel):
    producto_id: str = Field(..., description="Identificador único del producto")
    empresa_id: str = Field(..., description="Identificador de la empresa propietaria del producto")
    nombre_producto: str = Field(..., description="Nombre del producto")
    categoria_producto: str = Field(..., description="Categoría a la que pertenece el producto")
    estado_producto: str = Field(..., description="Estado actual del producto (e.g., activo, descontinuado)")
    fecha_lanzamiento: datetime = Field(..., description="Fecha de lanzamiento del producto")
    fecha_fin: Optional[datetime] = Field(None, description="Fecha de fin de vida del producto, si aplica")
    fecha_creacion: datetime = Field(..., description="Fecha de creación del registro del producto")
    fecha_actualizacion: Optional[datetime] = Field(None, description="Fecha de la última actualización del registro del producto")
    
    class Config:
        from_attributes = True
        orm_mode = True
        schema_extra = {
            "example": {
                "producto_id": "pr0001",
                "empresa_id": "ee0001",
                "nombre_producto": "Producto A",
                "categoria_producto": "Electrónica",
                "estado_producto": "Activo",
                "fecha_lanzamiento": "2023-01-15T00:00:00",
                "fecha_fin": None,
                "fecha_creacion": "2023-01-10T12:34:56",
                "fecha_actualizacion": "2023-02-20T09:21:45"
            }
        }
        
class ProductListResponse(BaseModel):
    products: list[ProductResponse]
    total: int
    page: int
    per_page: int
    
class ProductInternal(BaseModel):
    producto_id: str
    empresa_id: str
    nombre_producto: str
    categoria_producto: str
    estado_producto: str
    fecha_lanzamiento: datetime
    fecha_fin: Optional[datetime]
    fecha_creacion: datetime
    fecha_actualizacion: Optional[datetime]
    
    def to_dict(self):
        return {
            "producto_id": self.producto_id,
            "empresa_id": self.empresa_id,
            "nombre_producto": self.nombre_producto,
            "categoria_producto": self.categoria_producto,
            "estado_producto": self.estado_producto,
            "fecha_lanzamiento": self.fecha_lanzamiento,
            "fecha_fin": self.fecha_fin,
            "fecha_creacion": self.fecha_creacion,
            "fecha_actualizacion": self.fecha_actualizacion,
        }