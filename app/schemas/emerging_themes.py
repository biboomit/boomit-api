from pydantic import BaseModel, Field
from typing import List
from enum import Enum
from datetime import datetime


class ThemeRelevance(str, Enum):
    """Enum for theme relevance levels"""

    HIGH = "Alto"
    MEDIUM = "Medio"
    LOW = "Bajo"


class EmergingTheme(BaseModel):
    """Model for a single emerging theme identified from reviews"""

    tema: str = Field(
        ..., 
        description="Descripción del tema en 4-12 palabras",
        min_length=4,
        max_length=120
    )
    relevancia: ThemeRelevance = Field(
        ..., 
        description="Nivel de relevancia del tema: Alto, Medio, o Bajo"
    )
    indicacion: str = Field(
        ..., 
        description="Patrón común observado en las reviews (1-2 líneas)",
        min_length=10,
        max_length=500
    )
    frecuencia: int = Field(
        ..., 
        ge=3,
        description="Número de veces que el tema aparece en las reviews"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "tema": "Rechazo de tarjetas de débito en pagos recurrentes",
                "relevancia": "Alto",
                "indicacion": "Múltiples usuarios reportan que sus tarjetas de débito Visa son rechazadas al configurar pagos automáticos",
                "frecuencia": 47
            }
        }


class EmergingThemesAnalysisRequest(BaseModel):
    """Request model for emerging themes analysis"""

    app_id: str = Field(
        ..., 
        description="ID de la aplicación a analizar",
        min_length=1
    )
    force_new_analysis: bool = Field(
        default=False,
        description="Forzar nuevo análisis ignorando caché (útil para debug o actualización inmediata)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "app_id": "com.example.app",
                "force_new_analysis": False
            }
        }


class EmergingThemesAnalysisResponse(BaseModel):
    """Response model for emerging themes analysis - Async response with batch info"""

    batch_id: str = Field(
        ..., 
        description="ID del batch de OpenAI para monitorear el progreso"
    )
    status: str = Field(
        default="processing",
        description="Estado del análisis: processing, completed, failed"
    )
    app_id: str = Field(
        ..., 
        description="ID de la aplicación analizada"
    )
    app_name: str = Field(
        ..., 
        description="Nombre de la aplicación"
    )
    app_category: str = Field(
        ..., 
        description="Categoría de la aplicación"
    )
    total_reviews_analyzed: int = Field(
        ..., 
        ge=0,
        description="Número total de reviews enviadas para análisis"
    )
    analysis_period_start: datetime = Field(
        ..., 
        description="Fecha de inicio del período analizado"
    )
    analysis_period_end: datetime = Field(
        ..., 
        description="Fecha de fin del período analizado"
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Fecha y hora de creación del batch"
    )
    from_cache: bool = Field(
        default=False,
        description="Indica si el resultado proviene de caché (true) o es un análisis nuevo (false)"
    )
    cache_age_hours: float = Field(
        default=0.0,
        description="Edad del análisis en caché en horas (0 si es nuevo)"
    )
    message: str = Field(
        default="Análisis iniciado. El procesamiento puede tomar entre 2-6 horas. Use el batch_id para consultar el estado.",
        description="Mensaje informativo sobre el estado del análisis"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "batch_id": "batch_abc123xyz",
                "status": "processing",
                "app_id": "com.example.app",
                "app_name": "Mi App",
                "app_category": "Finanzas",
                "total_reviews_analyzed": 1247,
                "analysis_period_start": "2025-08-27T00:00:00Z",
                "analysis_period_end": "2025-11-25T23:59:59Z",
                "created_at": "2025-11-25T15:30:00Z",
                "from_cache": False,
                "cache_age_hours": 0.0,
                "message": "Análisis iniciado. El procesamiento puede tomar entre 2-6 horas. Use el batch_id para consultar el estado."
            }
        }


class EmergingThemesResult(BaseModel):
    """Final result model with identified themes"""

    app_id: str = Field(..., description="ID de la aplicación")
    app_name: str = Field(..., description="Nombre de la aplicación")
    app_category: str = Field(..., description="Categoría de la aplicación")
    total_reviews_analyzed: int = Field(..., ge=0)
    analysis_period_start: datetime
    analysis_period_end: datetime
    themes: List[EmergingTheme] = Field(
        default_factory=list,
        description="Lista de temas emergentes identificados"
    )
    analyzed_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Fecha y hora del análisis"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "app_id": "com.example.app",
                "app_name": "Mi App",
                "app_category": "Finanzas",
                "total_reviews_analyzed": 1247,
                "analysis_period_start": "2025-08-27T00:00:00Z",
                "analysis_period_end": "2025-11-25T23:59:59Z",
                "themes": [
                    {
                        "tema": "Rechazo de tarjetas de débito en pagos recurrentes",
                        "relevancia": "Alto",
                        "indicacion": "Múltiples usuarios reportan que sus tarjetas de débito Visa son rechazadas",
                        "frecuencia": 47
                    }
                ],
                "analyzed_at": "2025-11-25T15:30:00Z"
            }
        }
