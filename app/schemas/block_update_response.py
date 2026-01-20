from pydantic import BaseModel, Field


class BlockUpdateResponse(BaseModel):
    """Response para la actualización de blocks de un reporte"""
    message: str = Field(..., description="Mensaje de confirmación")
    report_id: str = Field(..., description="ID del reporte actualizado")
    blocks_count: int = Field(..., description="Cantidad de blocks actualizados")
    
    class Config:
        schema_extra = {
            "example": {
                "message": "Blocks actualizados exitosamente",
                "report_id": "4952c857-cce3-474c-aa9c-334ded01d01f",
                "blocks_count": 6
            }
        }
