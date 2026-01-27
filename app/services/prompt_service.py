"""
Servicio para gestión de prompts dinámicos.
Contiene la lógica de negocio para CRUD de prompts y validación.
"""
import logging
import json
from typing import List, Optional, Dict, Any
from google.cloud import bigquery

from app.models.prompt import PromptModel
from app.schemas.prompt import (
    PromptCreate,
    PromptResponse,
    PromptVersionResponse,
    PromptValidationRequest,
    PromptValidationResponse,
    PromptListResponse
)
from app.core.config import bigquery_config

logger = logging.getLogger(__name__)


class PromptService:
    """
    Servicio para gestionar prompts de OpenAI.
    Proporciona operaciones CRUD y validación de templates.
    """
    
    def __init__(self):
        """Inicializa el servicio con cliente de BigQuery"""
        self.client = bigquery_config.get_client()
        self.model = PromptModel(self.client)
        self._cache: Dict[str, str] = {}  # Cache simple en memoria {prompt_key: prompt_content}
        logger.info("[PROMPT_SERVICE] Servicio de prompts inicializado")
    
    async def create_prompt(self, prompt_data: PromptCreate) -> PromptResponse:
        """
        Crea una nueva versión de un prompt.
        
        Args:
            prompt_data: Datos del prompt a crear
            
        Returns:
            PromptResponse con los datos del prompt creado
        """
        logger.info(f"[PROMPT_SERVICE] Creando prompt: key={prompt_data.prompt_key}")
        
        # Validar el template antes de guardar
        validation = await self.validate_prompt(
            PromptValidationRequest(
                prompt_content=prompt_data.prompt_content,
                variables=prompt_data.variables
            )
        )
        
        if not validation.valid:
            logger.error(f"[PROMPT_SERVICE] Validación falló: {validation.message}")
            raise ValueError(f"Prompt inválido: {validation.message}")
        
        # Crear el prompt en BD
        try:
            row = self.model.create_prompt(
                prompt_key=prompt_data.prompt_key,
                prompt_content=prompt_data.prompt_content,
                variables=prompt_data.variables,
                description=prompt_data.description,
                created_by=prompt_data.created_by,
                validated=True,
                validation_error=None,
                auto_activate=prompt_data.auto_activate
            )
            
            # Invalidar cache si se activó automáticamente
            if prompt_data.auto_activate:
                self._invalidate_cache(prompt_data.prompt_key)
            
            # Parsear variables de JSON string a lista para la respuesta
            if isinstance(row.get('variables'), str):
                row['variables'] = json.loads(row['variables'])
            
            logger.info(f"[PROMPT_SERVICE] Prompt creado: id={row['prompt_id']}, version={row['prompt_version']}")
            return PromptResponse(**row)
            
        except Exception as e:
            logger.error(f"[PROMPT_SERVICE] Error al crear prompt: {e}")
            raise RuntimeError(f"Error al crear prompt: {str(e)}")
    
    async def get_active_prompt(self, prompt_key: str) -> str:
        """
        Obtiene el contenido del prompt activo.
        Usa cache para optimizar performance.
        
        Args:
            prompt_key: Identificador del tipo de prompt
            
        Returns:
            String con el contenido del prompt
            
        Raises:
            ValueError: Si no existe un prompt activo para ese key
        """
        logger.debug(f"[PROMPT_SERVICE] Obteniendo prompt activo: key={prompt_key}")
        
        # Verificar cache
        if prompt_key in self._cache:
            logger.debug(f"[PROMPT_SERVICE] Prompt encontrado en cache: key={prompt_key}")
            return self._cache[prompt_key]
        
        # Buscar en BD
        prompt_data = self.model.get_active_prompt(prompt_key)
        
        if not prompt_data:
            logger.error(f"[PROMPT_SERVICE] No existe prompt activo para key={prompt_key}")
            raise ValueError(f"No existe un prompt activo para el key '{prompt_key}'")
        
        # Guardar en cache
        self._cache[prompt_key] = prompt_data["prompt_content"]
        
        logger.info(f"[PROMPT_SERVICE] Prompt activo obtenido: key={prompt_key}, version={prompt_data['prompt_version']}")
        return prompt_data["prompt_content"]
    
    async def get_prompt_details(self, prompt_key: str) -> PromptResponse:
        """
        Obtiene todos los detalles del prompt activo.
        
        Args:
            prompt_key: Identificador del tipo de prompt
            
        Returns:
            PromptResponse con todos los datos
        """
        prompt_data = self.model.get_active_prompt(prompt_key)
        
        if not prompt_data:
            raise ValueError(f"No existe un prompt activo para el key '{prompt_key}'")
        
        return PromptResponse(**prompt_data)
    
    async def get_prompt_by_id(self, prompt_id: str) -> PromptResponse:
        """
        Obtiene un prompt específico por su ID.
        
        Args:
            prompt_id: UUID del prompt
            
        Returns:
            PromptResponse con los datos del prompt
        """
        prompt_data = self.model.get_prompt_by_id(prompt_id)
        
        if not prompt_data:
            raise ValueError(f"No existe un prompt con id '{prompt_id}'")
        
        return PromptResponse(**prompt_data)
    
    async def list_versions(
        self,
        prompt_key: str,
        page: int = 1,
        page_size: int = 20
    ) -> PromptListResponse:
        """
        Lista todas las versiones de un prompt con paginación.
        
        Args:
            prompt_key: Identificador del tipo de prompt
            page: Número de página (1-indexed)
            page_size: Tamaño de página
            
        Returns:
            PromptListResponse con las versiones
        """
        logger.info(f"[PROMPT_SERVICE] Listando versiones: key={prompt_key}, page={page}")
        
        offset = (page - 1) * page_size
        versions_data = self.model.list_versions(prompt_key, limit=page_size, offset=offset)
        
        # Convertir a PromptVersionResponse (sin content completo)
        versions = []
        for v in versions_data:
            version_response = PromptVersionResponse(
                prompt_id=v["prompt_id"],
                prompt_key=v["prompt_key"],
                prompt_version=v["prompt_version"],
                description=v["description"],
                is_active=v["is_active"],
                created_by=v["created_by"],
                created_at=v["created_at"],
                validated=v["validated"],
                variables=v["variables"],
                content_preview=v["prompt_content"][:200] + "..." if len(v["prompt_content"]) > 200 else v["prompt_content"]
            )
            versions.append(version_response)
        
        # Obtener total (simplificado: si hay menos de page_size, es la última página)
        total = offset + len(versions_data)
        if len(versions_data) == page_size:
            total += 1  # Indica que hay más páginas
        
        return PromptListResponse(
            total=total,
            versions=versions,
            page=page,
            page_size=page_size
        )
    
    async def activate_version(self, prompt_id: str) -> PromptResponse:
        """
        Activa una versión específica de un prompt.
        
        Args:
            prompt_id: UUID del prompt a activar
            
        Returns:
            PromptResponse con los datos del prompt activado
        """
        logger.info(f"[PROMPT_SERVICE] Activando versión: id={prompt_id}")
        
        # Activar la versión
        self.model.activate_version(prompt_id)
        
        # Obtener datos actualizados
        prompt_data = self.model.get_prompt_by_id(prompt_id)
        
        # Invalidar cache
        self._invalidate_cache(prompt_data["prompt_key"])
        
        logger.info(f"[PROMPT_SERVICE] Versión activada: id={prompt_id}, key={prompt_data['prompt_key']}")
        return PromptResponse(**prompt_data)
    
    async def validate_prompt(
        self,
        validation_request: PromptValidationRequest
    ) -> PromptValidationResponse:
        """
        Valida un prompt sin guardarlo.
        Verifica sintaxis y variables.
        
        Args:
            validation_request: Datos del prompt a validar
            
        Returns:
            PromptValidationResponse con el resultado de la validación
        """
        logger.info("[PROMPT_SERVICE] Validando prompt...")
        
        prompt_content = validation_request.prompt_content
        expected_variables = set(validation_request.variables)
        
        # Preparar datos de ejemplo
        sample_data = validation_request.sample_data or self._get_mock_data(expected_variables)
        
        try:
            # Intentar renderizar el template
            rendered = prompt_content.format(**sample_data)
            
            # Detectar variables en el template usando regex simple
            import re
            found_variables = set(re.findall(r'\{(\w+)\}', prompt_content))
            
            # Verificar variables faltantes o extra
            missing = found_variables - expected_variables
            extra = expected_variables - found_variables
            
            if missing or extra:
                message = []
                if missing:
                    message.append(f"Variables en template pero no declaradas: {list(missing)}")
                if extra:
                    message.append(f"Variables declaradas pero no usadas en template: {list(extra)}")
                
                return PromptValidationResponse(
                    valid=False,
                    message="; ".join(message),
                    missing_variables=list(missing) if missing else None,
                    extra_variables=list(extra) if extra else None
                )
            
            # Todo OK
            preview = rendered[:500] + "..." if len(rendered) > 500 else rendered
            
            return PromptValidationResponse(
                valid=True,
                message="Prompt válido. Template renderizado correctamente.",
                rendered_preview=preview
            )
            
        except KeyError as e:
            # Falta una variable requerida
            return PromptValidationResponse(
                valid=False,
                message=f"Variable requerida faltante: {str(e)}",
                error_details=str(e)
            )
        except Exception as e:
            # Error de sintaxis u otro problema
            return PromptValidationResponse(
                valid=False,
                message=f"Error al validar template: {str(e)}",
                error_details=str(e)
            )
    
    def _invalidate_cache(self, prompt_key: str):
        """Invalida el cache para un prompt_key específico"""
        if prompt_key in self._cache:
            del self._cache[prompt_key]
            logger.debug(f"[PROMPT_SERVICE] Cache invalidado para key={prompt_key}")
    
    def _get_mock_data(self, variables: set) -> Dict[str, str]:
        """
        Genera datos mock para validación basados en las variables esperadas.
        
        Args:
            variables: Set de nombres de variables
            
        Returns:
            Dict con datos mock
        """
        mock_data = {}
        for var in variables:
            if "json" in var.lower() or "data" in var.lower():
                mock_data[var] = json.dumps({"sample": "data"})
            else:
                mock_data[var] = f"<{var}_value>"
        return mock_data
