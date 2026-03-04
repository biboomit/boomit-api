from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any


class HighchartsSpec(BaseModel):
    """Especificación de configuración de Highcharts"""
    chart: Optional[Dict[str, Any]] = Field(None, description="Configuración del tipo de gráfico")
    title: Optional[Dict[str, Any]] = Field(None, description="Título del gráfico")
    xAxis: Optional[Dict[str, Any]] = Field(None, description="Configuración del eje X")
    yAxis: Optional[Dict[str, Any]] = Field(None, description="Configuración del eje Y")
    series: Optional[List[Dict[str, Any]]] = Field(None, description="Series de datos")
    
    class Config:
        extra = "allow"  # Permite campos adicionales de Highcharts


class ChartBlock(BaseModel):
    """Estructura de un gráfico dentro de un bloque"""
    chart_title: str = Field(..., description="Título del gráfico")
    chart_description: str = Field(..., description="Descripción del gráfico")
    business_question: str = Field(..., description="Pregunta de negocio que responde el gráfico")
    highcharts_spec: HighchartsSpec = Field(..., description="Especificación de Highcharts para renderizar el gráfico")


class Block(BaseModel):
    """Estructura de un bloque de reporte"""
    block_key: str = Field(..., description="Clave identificadora del bloque")
    narrative: str = Field(..., description="Narrativa o descripción del bloque")
    insights: List[str] = Field(..., description="Lista de insights o hallazgos clave")
    charts: List[ChartBlock] = Field(default_factory=list, description="Lista de gráficos asociados al bloque")


class BlockUpdateRequest(BaseModel):
    """Request para actualizar el array de blocks de un reporte"""
    blocks: List[Block] = Field(..., description="Array completo de blocks que reemplazará los existentes")
    
    class Config:
        schema_extra = {
            "example": {
                "blocks": [
                    {
                        "block_key": "resumen_ejecutivo",
                        "narrative": "Este reporte presenta una visión general...",
                        "insights": [
                            "Se invirtió un total de 8754.94 en campañas digitales...",
                            "El CPA promedio fue de 1.12..."
                        ],
                        "charts": [
                            {
                                "chart_title": "Inversión vs Instalaciones",
                                "chart_description": "Gráfico que muestra la relación...",
                                "business_question": "¿Cuál fue la eficacia de la inversión?",
                                "highcharts_spec": {
                                    "chart": {"type": "column"},
                                    "title": {"text": "Inversión vs Instalaciones"},
                                    "series": [{"name": "Inversión", "data": [8754.94]}]
                                }
                            }
                        ]
                    }
                ]
            }
        }
