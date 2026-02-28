"""
Endpoints API REST para gestión de prompts dinámicos.
Permite CRUD de prompts, versionado, activación y validación.
"""
import json
import logging
import re
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, status, File, UploadFile, Form
from fastapi.responses import JSONResponse, Response

from app.schemas.prompt import (
    PromptCreate,
    PromptResponse,
    PromptValidationRequest,
    PromptValidationResponse,
    PromptListResponse,
    PromptActivateRequest
)
from app.services.prompt_service import PromptService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/prompts", tags=["prompts"])


@router.post(
    "",
    response_model=PromptResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear nueva versión de prompt",
    description="""
    Crea una nueva versión de un prompt.
    
    - Valida el template automáticamente antes de guardar
    - Por defecto activa la nueva versión (auto_activate=true)
    - Incrementa automáticamente el número de versión
    - Desactiva versiones anteriores si auto_activate=true
    """
)
async def create_prompt(prompt_data: PromptCreate) -> PromptResponse:
    """
    Crea una nueva versión de un prompt.
    
    **Ejemplo de request:**
    ```json
    {
      "prompt_key": "report_generation_highchart",
      "prompt_content": "Genera un reporte con {analytics_data} y {report_config}",
      "variables": ["analytics_data", "report_config"],
      "description": "Mejoré la sección de conclusiones",
      "created_by": "po@boomit.com",
      "auto_activate": true
    }
    ```
    """
    logger.info(f"[API_PROMPTS] POST /prompts - Creando prompt: key={prompt_data.prompt_key}")
    
    service = PromptService()
    
    try:
        result = await service.create_prompt(prompt_data)
        logger.info(f"[API_PROMPTS] Prompt creado exitosamente: id={result.prompt_id}")
        return result
    except ValueError as e:
        logger.error(f"[API_PROMPTS] Error de validación: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"[API_PROMPTS] Error inesperado: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al crear prompt: {str(e)}"
        )


@router.get(
    "/{prompt_key}",
    response_model=PromptResponse,
    summary="Obtener prompt activo",
    description="Obtiene el prompt activo para un prompt_key específico con todos sus detalles."
)
async def get_active_prompt(prompt_key: str) -> PromptResponse:
    """
    Obtiene el prompt activo para un prompt_key.
    
    **Parámetros:**
    - `prompt_key`: Identificador del tipo de prompt (ej: "report_generation_highchart")
    """
    logger.info(f"[API_PROMPTS] GET /prompts/{prompt_key}")
    
    service = PromptService()
    
    try:
        result = await service.get_prompt_details(prompt_key)
        return result
    except ValueError as e:
        logger.warning(f"[API_PROMPTS] Prompt no encontrado: {e}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"[API_PROMPTS] Error inesperado: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al obtener prompt: {str(e)}"
        )


@router.get(
    "/{prompt_key}/versions",
    response_model=PromptListResponse,
    summary="Listar versiones de un prompt",
    description="Lista todas las versiones de un prompt con paginación, ordenadas de más reciente a más antigua."
)
async def list_prompt_versions(
    prompt_key: str,
    page: int = Query(default=1, ge=1, description="Número de página (1-indexed)"),
    page_size: int = Query(default=20, ge=1, le=100, description="Tamaño de página (máx 100)")
) -> PromptListResponse:
    """
    Lista todas las versiones de un prompt.
    
    **Parámetros:**
    - `prompt_key`: Identificador del tipo de prompt
    - `page`: Número de página (default: 1)
    - `page_size`: Resultados por página (default: 20, máx: 100)
    """
    logger.info(f"[API_PROMPTS] GET /prompts/{prompt_key}/versions - page={page}, size={page_size}")
    
    service = PromptService()
    
    try:
        result = await service.list_versions(prompt_key, page=page, page_size=page_size)
        return result
    except Exception as e:
        logger.error(f"[API_PROMPTS] Error al listar versiones: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al listar versiones: {str(e)}"
        )


@router.put(
    "/{prompt_id}/activate",
    response_model=PromptResponse,
    summary="Activar versión específica",
    description="""
    Activa una versión específica de un prompt.
    
    - Desactiva automáticamente todas las demás versiones del mismo prompt_key
    - Invalida el cache para forzar la recarga
    - Útil para hacer rollback a versiones anteriores
    """
)
async def activate_prompt_version(prompt_id: str) -> PromptResponse:
    """
    Activa una versión específica de un prompt.
    
    **Parámetros:**
    - `prompt_id`: UUID del prompt a activar
    
    **Ejemplo:**
    ```
    PUT /api/v1/prompts/abc-123-def-456/activate
    ```
    """
    logger.info(f"[API_PROMPTS] PUT /prompts/{prompt_id}/activate")
    
    service = PromptService()
    
    try:
        result = await service.activate_version(prompt_id)
        logger.info(f"[API_PROMPTS] Versión activada: id={prompt_id}, key={result.prompt_key}")
        return result
    except ValueError as e:
        logger.warning(f"[API_PROMPTS] Prompt no encontrado: {e}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"[API_PROMPTS] Error al activar versión: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al activar versión: {str(e)}"
        )


@router.get(
    "/id/{prompt_id}",
    response_model=PromptResponse,
    summary="Obtener prompt por ID",
    description="Obtiene un prompt específico por su UUID, sin importar si está activo o no."
)
async def get_prompt_by_id(prompt_id: str) -> PromptResponse:
    """
    Obtiene un prompt específico por su ID.
    
    **Parámetros:**
    - `prompt_id`: UUID del prompt
    """
    logger.info(f"[API_PROMPTS] GET /prompts/id/{prompt_id}")
    
    service = PromptService()
    
    try:
        result = await service.get_prompt_by_id(prompt_id)
        return result
    except ValueError as e:
        logger.warning(f"[API_PROMPTS] Prompt no encontrado: {e}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"[API_PROMPTS] Error al obtener prompt: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al obtener prompt: {str(e)}"
        )


@router.get(
    "/health",
    summary="Health check del servicio de prompts",
    description="Verifica conectividad con BigQuery y estado del servicio."
)
async def health_check():
    """
    Verifica que el servicio de prompts esté funcionando.
    """
    try:
        service = PromptService()
        # Intentar una query simple
        service.client.query("SELECT 1 as test").result()
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "status": "healthy",
                "message": "Servicio de prompts operativo. Conexión a BigQuery OK.",
                "service": "prompt_service"
            }
        )
    except Exception as e:
        logger.error(f"[API_PROMPTS] Health check falló: {e}")
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "unhealthy",
                "message": f"Error de conectividad: {str(e)}",
                "service": "prompt_service"
            }
        )


@router.post(
    "/upload",
    response_model=PromptResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear prompt desde archivo Python",
    description="""
    Crear nueva versión de prompt subiendo un archivo .py directamente.
    
    - El archivo debe contener: REPORT_GENERATION_PROMPT = '''...'''
    - Útil para prompts largos (>100 líneas)
    - Evita problemas de escape de caracteres en JSON
    - El PO puede editar el archivo localmente y subirlo
    """
)
async def create_prompt_from_python_file(
    file: UploadFile = File(..., description="Archivo .py con REPORT_GENERATION_PROMPT"),
    prompt_key: str = Form(..., description="Identificador del prompt"),
    description: str = Form(..., description="Descripción de los cambios"),
    created_by: str = Form(..., description="Email del creador"),
    auto_activate: bool = Form(default=True, description="Activar automáticamente")
):
    """
    Crear prompt desde archivo Python (.py).
    
    **Uso en Postman:**
    - Method: POST
    - Body: form-data
    - file: [Seleccionar archivo .py]
    - prompt_key: "report_generation_highchart"
    - description: "Nueva versión con mejoras"
    - created_by: "po@boomit.com"
    - auto_activate: true
    
    **Formato del archivo .py:**
    ```python
    REPORT_GENERATION_PROMPT = '''
    Tu prompt aquí
    con múltiples líneas
    sin preocuparte por escapes
    '''
    ```
    """
    logger.info(f"[API_PROMPTS] POST /prompts/upload-py - file={file.filename}, key={prompt_key}")
    
    service = PromptService()
    
    try:
        # Validar extensión
        if not file.filename.endswith('.py'):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El archivo debe tener extensión .py"
            )
        
        # Leer contenido del archivo
        content = await file.read()
        text = content.decode('utf-8')
        
        # Validar que contenga el prompt
        if 'REPORT_GENERATION_PROMPT = ' not in text:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El archivo debe contener REPORT_GENERATION_PROMPT = '''...'''"
            )
        
        # Extraer el contenido del prompt
        logger.debug(f"[API_PROMPTS] Extrayendo prompt de {file.filename}...")
        
        # Buscar el inicio del prompt
        prompt_start = text.find('REPORT_GENERATION_PROMPT = ')
        if prompt_start == -1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No se encontró REPORT_GENERATION_PROMPT en el archivo"
            )
        
        # Extraer desde el signo = hasta el final
        prompt_section = text[prompt_start:].split('=', 1)[1].strip()
        
        # Detectar el tipo de comillas (''' o """)
        if prompt_section.startswith("'''"):
            quote_type = "'''"
            prompt_content = prompt_section[3:]  # Remover comillas iniciales
            # Buscar las comillas finales
            end_pos = prompt_content.find("'''")
            if end_pos != -1:
                prompt_content = prompt_content[:end_pos]
        elif prompt_section.startswith('"""'):
            quote_type = '"""'
            prompt_content = prompt_section[3:]
            end_pos = prompt_content.find('"""')
            if end_pos != -1:
                prompt_content = prompt_content[:end_pos]
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El prompt debe usar comillas triples (''' o \"\"\")"
            )
        
        # Limpiar espacios
        prompt_content = prompt_content.strip()
        
        if not prompt_content:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El contenido del prompt está vacío"
            )
        
        logger.info(f"[API_PROMPTS] Prompt extraído: {len(prompt_content)} caracteres")
        
        # Detectar automáticamente las variables en el prompt
        detected_variables = list(set(re.findall(r'\{(\w+)\}', prompt_content)))
        logger.info(f"[API_PROMPTS] Variables detectadas: {detected_variables}")
        
        # Crear el prompt en la BD
        prompt_data = PromptCreate(
            prompt_key=prompt_key,
            prompt_content=prompt_content,
            variables=detected_variables,
            description=description,
            created_by=created_by,
            auto_activate=auto_activate
        )
        
        result = await service.create_prompt(prompt_data)
        
        logger.info(f"[API_PROMPTS] Prompt creado desde archivo: id={result.prompt_id}, version={result.prompt_version}")
        
        return result
        
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"[API_PROMPTS] Error de validación: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"[API_PROMPTS] Error al procesar archivo: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al procesar archivo .py: {str(e)}"
        )


@router.get(
    "/download",
    summary="Descargar prompt activo como archivo Python",
    description="""
    Descarga el prompt activo en formato .py para editarlo localmente.
    
    - Retorna un archivo .py listo para editar
    - Mantiene el formato REPORT_GENERATION_PROMPT = '''...'''
    - Útil para el flujo: download → editar → upload
    """
)
async def download_active_prompt():
    """
    Descargar el prompt activo como archivo .py
    
    **Uso en Postman:**
    - Method: GET
    - URL: /api/v1/prompts/download
    - Send and Download
    
    **Flujo recomendado:**
    1. GET /prompts/download → Descargar archivo
    2. Editar localmente en VS Code
    3. POST /prompts/upload-py → Subir nueva versión
    """
    logger.info(f"[API_PROMPTS] GET /prompts/download")
    
    service = PromptService()
    
    try:
        # Obtener el prompt activo
        prompt_content = await service.get_active_prompt()
        
        # Generar contenido del archivo Python
        file_content = f"""# Prompt para OpenAI 
# Versión: {prompt_content.prompt_version}
# Creado por: {prompt_content.created_by}
# Fecha: {prompt_content.created_at}
# Descripción: {prompt_content.description or 'N/A'}

REPORT_GENERATION_PROMPT = '''
{prompt_content.prompt_content}
'''.strip()
"""
        
        # Retornar como archivo descargable
        return Response(
            content=file_content,
            media_type="text/x-python",
            headers={
                "Content-Disposition": f"attachment; filename=active_prompt_v{prompt_content.prompt_version}.py"
            }
        )
        
    except ValueError as e:
        logger.warning(f"[API_PROMPTS] Prompt no encontrado: {e}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"[API_PROMPTS] Error al generar descarga: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al generar archivo de descarga: {str(e)}"
        )
