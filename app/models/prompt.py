"""
Modelo de datos para Prompts dinámicos almacenados en BigQuery.
"""
import json
import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any
from google.cloud import bigquery
import logging

logger = logging.getLogger(__name__)


class PromptModel:
    """
    Modelo para gestionar prompts de OpenAI en BigQuery.
    Permite versionado, activación y rollback de prompts sin modificar código.
    """
    
    TABLE_ID = "marketing-dwh-specs.DWH.AI_PROMPTS"
    
    def __init__(self, client: bigquery.Client):
        """
        Args:
            client: Cliente de BigQuery inicializado
        """
        self.client = client
    
    def create_prompt(
        self,
        prompt_key: str,
        prompt_content: str,
        variables: List[str],
        description: str,
        created_by: str,
        validated: bool = True,
        validation_error: Optional[str] = None,
        auto_activate: bool = True
    ) -> Dict[str, Any]:
        """
        Crea una nueva versión de un prompt.
        
        Args:
            prompt_key: Identificador del tipo de prompt
            prompt_content: Contenido del template
            variables: Lista de variables requeridas
            description: Descripción del cambio
            created_by: Email del creador
            validated: Si el prompt fue validado
            validation_error: Error de validación si aplica
            auto_activate: Si debe activarse automáticamente
            
        Returns:
            Dict con los datos del prompt creado
        """
        logger.info(f"[PROMPT_MODEL] Creando nuevo prompt: key={prompt_key}, auto_activate={auto_activate}")
        
        # Obtener la siguiente versión
        next_version = self._get_next_version(prompt_key)
        

        # Generar ID único
        prompt_id = str(uuid.uuid4())
        
        # Preparar datos (convertir lista a JSON para BigQuery)
        row = {
            "prompt_id": prompt_id,
            "prompt_key": prompt_key,
            "prompt_version": next_version,
            "prompt_content": prompt_content,
            "variables": json.dumps(variables),  # Convertir a JSON string
            "description": description,
            "is_active": auto_activate,
            "created_by": created_by,
            "created_at": datetime.utcnow().isoformat(),
            "validated": validated,
            "validation_error": validation_error
        }
        
        # Insertar en BigQuery
        errors = self.client.insert_rows_json(self.TABLE_ID, [row])
        
        if errors:
            logger.error(f"[PROMPT_MODEL] Error al insertar prompt: {errors}")
            raise RuntimeError(f"Error al crear prompt en BigQuery: {errors}")
        
        # Si auto_activate, desactivar versiones anteriores (excluyendo el recién creado)
        if auto_activate:
            self._deactivate_all_versions(prompt_key, except_prompt_id=prompt_id)
        
        logger.info(f"[PROMPT_MODEL] Prompt creado exitosamente: id={prompt_id}, version={next_version}")
        return row
    
    def get_active_prompt(self, prompt_key: str) -> Optional[Dict[str, Any]]:
        """
        Obtiene el prompt activo para un prompt_key dado.
        
        Args:
            prompt_key: Identificador del tipo de prompt
            
        Returns:
            Dict con los datos del prompt activo o None si no existe
        """
        logger.debug(f"[PROMPT_MODEL] Buscando prompt activo: key={prompt_key}")
        
        query = f"""
        SELECT *
        FROM `{self.TABLE_ID}`
        WHERE prompt_key = @prompt_key
          AND is_active = true
        ORDER BY prompt_version DESC
        LIMIT 1
        """
        
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("prompt_key", "STRING", prompt_key)
            ]
        )
        
        query_job = self.client.query(query, job_config=job_config)
        results = list(query_job.result())
        
        if not results:
            logger.warning(f"[PROMPT_MODEL] No se encontró prompt activo para key={prompt_key}")
            return None
        
        row = results[0]
        return self._row_to_dict(row)
    
    def get_prompt_by_id(self, prompt_id: str) -> Optional[Dict[str, Any]]:
        """
        Obtiene un prompt por su ID.
        
        Args:
            prompt_id: UUID del prompt
            
        Returns:
            Dict con los datos del prompt o None
        """
        query = f"""
        SELECT *
        FROM `{self.TABLE_ID}`
        WHERE prompt_id = @prompt_id
        LIMIT 1
        """
        
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("prompt_id", "STRING", prompt_id)
            ]
        )
        
        query_job = self.client.query(query, job_config=job_config)
        results = list(query_job.result())
        
        if not results:
            return None
        
        return self._row_to_dict(results[0])
    
    def list_versions(
        self,
        prompt_key: str,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Lista todas las versiones de un prompt ordenadas por versión descendente.
        
        Args:
            prompt_key: Identificador del tipo de prompt
            limit: Número máximo de resultados
            offset: Offset para paginación
            
        Returns:
            Lista de dicts con versiones del prompt
        """
        logger.debug(f"[PROMPT_MODEL] Listando versiones: key={prompt_key}, limit={limit}")
        
        query = f"""
        SELECT *
        FROM `{self.TABLE_ID}`
        WHERE prompt_key = @prompt_key
        ORDER BY prompt_version DESC
        LIMIT @limit
        OFFSET @offset
        """
        
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("prompt_key", "STRING", prompt_key),
                bigquery.ScalarQueryParameter("limit", "INT64", limit),
                bigquery.ScalarQueryParameter("offset", "INT64", offset)
            ]
        )
        
        query_job = self.client.query(query, job_config=job_config)
        results = list(query_job.result())
        
        return [self._row_to_dict(row) for row in results]
    
    def activate_version(self, prompt_id: str) -> bool:
        """
        Activa una versión específica de un prompt y desactiva las demás.
        
        Args:
            prompt_id: UUID del prompt a activar
            
        Returns:
            True si se activó correctamente
        """
        logger.info(f"[PROMPT_MODEL] Activando versión: id={prompt_id}")
        
        # Obtener el prompt
        prompt = self.get_prompt_by_id(prompt_id)
        if not prompt:
            logger.error(f"[PROMPT_MODEL] Prompt no encontrado: id={prompt_id}")
            raise ValueError(f"Prompt con id {prompt_id} no encontrado")
        
        prompt_key = prompt["prompt_key"]
        
        # Desactivar otras versiones (excluyendo la que vamos a activar)
        self._deactivate_all_versions(prompt_key, except_prompt_id=prompt_id)
        
        # Activar la versión solicitada
        update_query = f"""
        UPDATE `{self.TABLE_ID}`
        SET is_active = true
        WHERE prompt_id = @prompt_id
        """
        
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("prompt_id", "STRING", prompt_id)
            ]
        )
        
        query_job = self.client.query(update_query, job_config=job_config)
        query_job.result()  # Esperar a que termine
        
        logger.info(f"[PROMPT_MODEL] Versión activada: id={prompt_id}")
        return True
    
    def _get_next_version(self, prompt_key: str) -> int:
        """
        Obtiene el siguiente número de versión para un prompt_key.
        
        Args:
            prompt_key: Identificador del tipo de prompt
            
        Returns:
            Número de la siguiente versión
        """
        query = f"""
        SELECT COALESCE(MAX(prompt_version), 0) + 1 as next_version
        FROM `{self.TABLE_ID}`
        WHERE prompt_key = @prompt_key
        """
        
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("prompt_key", "STRING", prompt_key)
            ]
        )
        
        query_job = self.client.query(query, job_config=job_config)
        results = list(query_job.result())
        
        return results[0]["next_version"]
    
    def _deactivate_all_versions(self, prompt_key: str, except_prompt_id: Optional[str] = None):
        """
        Desactiva todas las versiones de un prompt_key.
        
        Args:
            prompt_key: Identificador del tipo de prompt
            except_prompt_id: ID del prompt a excluir del UPDATE (típicamente el recién creado)
        """
        logger.debug(f"[PROMPT_MODEL] Desactivando todas las versiones: key={prompt_key}, except={except_prompt_id}")
        
        # Construir query excluyendo el prompt recién creado si se especifica
        where_clause = "WHERE prompt_key = @prompt_key AND is_active = true"
        if except_prompt_id:
            where_clause += " AND prompt_id != @except_prompt_id"
        
        update_query = f"""
        UPDATE `{self.TABLE_ID}`
        SET is_active = false
        {where_clause}
        """
        
        query_parameters = [
            bigquery.ScalarQueryParameter("prompt_key", "STRING", prompt_key)
        ]
        if except_prompt_id:
            query_parameters.append(
                bigquery.ScalarQueryParameter("except_prompt_id", "STRING", except_prompt_id)
            )
        
        job_config = bigquery.QueryJobConfig(query_parameters=query_parameters)
        
        query_job = self.client.query(update_query, job_config=job_config)
        query_job.result()  # Esperar a que termine
    
    def _row_to_dict(self, row) -> Dict[str, Any]:
        """
        Convierte una fila de BigQuery a diccionario.
        
        Args:
            row: Fila de BigQuery
            
        Returns:
            Dict con los datos de la fila
        """
        # Parsear variables de JSON string a lista
        variables = row.variables
        if isinstance(variables, str):
            try:
                variables = json.loads(variables)
            except:
                variables = []
        
        return {
            "prompt_id": row.prompt_id,
            "prompt_key": row.prompt_key,
            "prompt_version": row.prompt_version,
            "prompt_content": row.prompt_content,
            "variables": variables,
            "description": row.description,
            "is_active": row.is_active,
            "created_by": row.created_by,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "validated": row.validated,
            "validation_error": row.validation_error
        }
