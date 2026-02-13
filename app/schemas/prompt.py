"""
Schemas Pydantic para validación de requests/responses de Prompts.
"""
from pydantic import BaseModel, Field, field_validator
from typing import List, Optional
from datetime import datetime


class PromptBase(BaseModel):
    """Schema base para Prompt"""
    prompt_key: str = Field(..., description="Identificador del tipo de prompt (ej: report_generation_highchart)")
    prompt_content: str = Field(..., min_length=10, description="Contenido completo del template del prompt")
    variables: List[str] = Field(..., description="Lista de variables requeridas en el template")
    description: Optional[str] = Field(None, description="Descripción del cambio realizado")
    
    @field_validator("variables")
    @classmethod
    def validate_variables(cls, v):
        """Valida que haya al menos una variable"""
        if not v or len(v) == 0:
            raise ValueError("Debe especificar al menos una variable")
        return v


class PromptCreate(PromptBase):
    """Schema para crear un nuevo prompt"""
    created_by: str = Field(..., description="Email del usuario que crea el prompt")
    auto_activate: bool = Field(default=True, description="Si debe activarse automáticamente")
    
    @field_validator("created_by")
    @classmethod
    def validate_email(cls, v):
        """Validación básica de email"""
        if "@" not in v:
            raise ValueError("created_by debe ser un email válido")
        return v


class PromptUpdate(BaseModel):
    """Schema para actualizar un prompt (solo ciertos campos)"""
    description: Optional[str] = None


class PromptResponse(BaseModel):
    """Schema para respuesta de un prompt"""
    prompt_id: str
    prompt_key: str
    prompt_version: int
    prompt_content: str
    variables: List[str]
    description: Optional[str]
    is_active: bool
    created_by: str
    created_at: str  # ISO format
    validated: bool
    validation_error: Optional[str]
    
    class Config:
        from_attributes = True


class PromptVersionResponse(BaseModel):
    """Schema para listado de versiones (sin el content completo)"""
    prompt_id: str
    prompt_key: str
    prompt_version: int
    description: Optional[str]
    is_active: bool
    created_by: str
    created_at: str
    validated: bool
    variables: List[str]
    content_preview: str = Field(..., description="Primeros 200 caracteres del prompt")
    
    class Config:
        from_attributes = True


class PromptValidationRequest(BaseModel):
    """Schema para validar un prompt sin guardarlo"""
    prompt_content: str = Field(..., min_length=10)
    variables: List[str]
    sample_data: Optional[dict] = Field(
        default=None,
        description="Datos de ejemplo para probar el template. Si no se provee, se usan datos mock."
    )


class PromptValidationResponse(BaseModel):
    """Schema para respuesta de validación"""
    valid: bool
    message: str
    missing_variables: Optional[List[str]] = None
    extra_variables: Optional[List[str]] = None
    rendered_preview: Optional[str] = Field(None, description="Preview del prompt renderizado (primeros 500 chars)")
    error_details: Optional[str] = None


class PromptActivateRequest(BaseModel):
    """Schema para activar una versión específica"""
    prompt_id: str = Field(..., description="UUID del prompt a activar")


class PromptListResponse(BaseModel):
    """Schema para listado paginado de prompts"""
    total: int
    versions: List[PromptVersionResponse]
    page: int
    page_size: int


class PromptStatsResponse(BaseModel):
    """Schema para estadísticas de un prompt_key"""
    prompt_key: str
    total_versions: int
    active_version: Optional[int]
    last_updated: Optional[str]
    created_by_users: List[str]
