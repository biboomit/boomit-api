import json
import os
from datetime import datetime, timedelta
from uuid import uuid4
from app.core.config import bigquery_config
from app.integrations.openai.report_generation_integration import OpenAIReportGenerationIntegration
from app.integrations.gcp.identity_token_client import GCPIdentityTokenClient
from app.services.analytics_providers import get_analytics_provider
from google.cloud import bigquery
import logging

logger = logging.getLogger(__name__)

class ReportGenerationService:
    
    def __init__(self):
        logger.info("🚀 [SERVICE] ReportGenerationService INIT")
        self.client = bigquery_config.get_client()
        self.agent_table = bigquery_config.get_table_id("DIM_AI_REPORT_AGENT_CONFIGS")
        self.reports_table = bigquery_config.get_table_id_with_dataset(
            "AIOutput", "AI_MARKETING_REPORTS")
        self.openai = OpenAIReportGenerationIntegration()
        self.gcp_auth_client = GCPIdentityTokenClient()

    def generate_report(self, agent_id: str, user_id: str, date_from: str = None, date_to: str = None, top_n: int = 10) -> str:
        logger.info(f"📝 [SERVICE] generate_report IN: agent_id={agent_id}, user_id={user_id}, top_n={top_n}")
        # 1. Consultar configuración del agente
        agent_config = self._get_agent_config(agent_id, user_id)

        # 2. Resolver el proveedor de analytics según la configuración del agente
        provider_name = agent_config.get("company")
        if not provider_name:
            raise ValueError("El agente no tiene configurado un company name en la configuración del reporte.")
        formatted_provider_name = provider_name.lower().replace(" ", "_")
        analytics_provider = get_analytics_provider(formatted_provider_name)

        # 3. Consultar datos analíticos via el proveedor (data + data_window + explicación)
        analytics_data, data_window, analytics_explanation = analytics_provider.get_analytics(
            date_from=date_from, date_to=date_to, top_n=top_n
        )

        # 4. Validar que el prompt se puede construir antes de gastar tokens
        prompt_ok = self.openai.validate_prompt(
            analytics_data=analytics_data,
            agent_config=agent_config,
            data_window=data_window,
            analytics_explanation=analytics_explanation,
        )
        if not prompt_ok:
            raise RuntimeError("El prompt no se pudo construir correctamente. Revisa los datos de entrada y la configuración del agente antes de hacer la llamada a OpenAI.")

        # 5. Llamar a OpenAI para generar el reporte, pasando data_window y la explicación
        report_json = self.openai.generate_report(
            analytics_data=analytics_data,
            agent_config=agent_config,
            data_window=data_window,
            analytics_explanation=analytics_explanation,
        )

        if not isinstance(report_json, dict):
            logger.error(f"[OPENAI ERROR] El resultado de OpenAI no es un dict: {type(report_json)}: {str(report_json)[:1000]}")
            raise RuntimeError(f"El resultado de OpenAI no es un dict: {type(report_json)}: {str(report_json)[:1000]}")

        # 6. Guardar el reporte generado y retornar el ID
        report_id = self._save_report(agent_id, user_id, report_json, date_from, date_to)

        # 7. Retornar mensaje de exito y report_id
        return {
            "message": f"Successfully generated report structure for agent_id: {agent_id}, user_id: {user_id}",
            "report_id": report_id,
        }

    def _get_agent_config(self, agent_id, user_id):
        logger.info(f"🔍 [SERVICE] _get_agent_config IN: agent_id={agent_id}, user_id={user_id}")
        query = f"SELECT company, config_context, attribution_source, marketing_funnel, color_palette, selected_blocks, blocks_config FROM `{self.agent_table}` WHERE id = @agent_id AND user_id = @user_id LIMIT 1"
        job_config = bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("agent_id", "STRING", agent_id),
            bigquery.ScalarQueryParameter("user_id", "STRING", user_id)
        ])
        result = list(self.client.query(query, job_config=job_config).result())
        if not result:
            logger.warning(f"🔍 [SERVICE] _get_agent_config OUT: not found")
            raise ValueError("No se encontró la configuración del agente.")
        logger.info(f"🔍 [SERVICE] _get_agent_config OUT: found config")
        return dict(result[0])

    def _save_report(self, agent_id, user_id, report_json, date_from, date_to):
        logger.info(f"💾 [SERVICE] _save_report IN: agent_id={agent_id}, user_id={user_id} period to analyze: {date_from} to {date_to}")
        now = datetime.utcnow().isoformat()
        report_id = str(uuid4())
        
        # Convert date strings to timestamp format if provided (BigQuery expects YYYY-MM-DD HH:MM:SS)
        date_from_ts = None
        if date_from:
            try:
                # If it's just a date (YYYY-MM-DD), add time component
                if len(date_from) == 10:  # Format: YYYY-MM-DD
                    date_from_ts = f"{date_from} 00:00:00"
                else:
                    date_from_ts = date_from
            except Exception as e:
                logger.warning(f"Error parsing date_from: {e}, using None")
        
        date_to_ts = None
        if date_to:
            try:
                # If it's just a date (YYYY-MM-DD), add time component
                if len(date_to) == 10:  # Format: YYYY-MM-DD
                    date_to_ts = f"{date_to} 23:59:59"
                else:
                    date_to_ts = date_to
            except Exception as e:
                logger.warning(f"Error parsing date_to: {e}, using None")
        
        row = {
            "report_id": report_id,
            "agent_config_id": agent_id,
            "user_id": user_id,
            "report_json": json.dumps(report_json, ensure_ascii=False) if not isinstance(report_json, str) else report_json,
            "generated_at": now,
            "date_from": date_from_ts,
            "date_to": date_to_ts
        }
        errors = self.client.insert_rows_json(self.reports_table, [row])
        if errors:
            logger.error(f"💾 [SERVICE] _save_report OUT: error {errors}")
            raise RuntimeError(f"Error al guardar el reporte: {errors}")
        logger.info(f"💾 [SERVICE] _save_report OUT: guardado exitosamente para agent_id: {agent_id}, user_id: {user_id}, report_id: {report_id}")
        return report_id

    def get_latest_report(self, agent_config_id: str, user_id: str) -> dict:
        """
        Obtiene el reporte más reciente para un agent_config_id y user_id específicos.
        
        Args:
            agent_config_id: ID de la configuración del agente
            user_id: ID del usuario
            
        Returns:
            dict: Información del reporte más reciente incluyendo report_id, agent_config_id, generated_at y report_json
            
        Raises:
            ValueError: Si no se encuentra ningún reporte para los parámetros dados
        """
        logger.info(f"🔍 [SERVICE] get_latest_report IN: agent_config_id={agent_config_id}, user_id={user_id}")
        
        query = f"""
        SELECT report_id, agent_config_id, generated_at, report_json
        FROM `{self.reports_table}`
        WHERE agent_config_id = @agent_config_id AND user_id = @user_id
        ORDER BY generated_at DESC
        LIMIT 1
        """
        
        job_config = bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("agent_config_id", "STRING", agent_config_id),
            bigquery.ScalarQueryParameter("user_id", "STRING", user_id)
        ])
        
        result = list(self.client.query(query, job_config=job_config).result())
        
        if not result:
            logger.warning(f"🔍 [SERVICE] get_latest_report OUT: no report found")
            raise ValueError(f"No se encontró ningún reporte para agent_config_id: {agent_config_id}")
        
        row = dict(result[0])
        logger.info(f"🔍 [SERVICE] get_latest_report OUT: found report_id={row['report_id']}")
        
        # Parse report_json if it's a string
        report_json = row["report_json"]
        if isinstance(report_json, str):
            try:
                report_json = json.loads(report_json)
            except json.JSONDecodeError as e:
                logger.error(f"Error parsing report_json: {e}")
                report_json = {}
        
        # Convert generated_at datetime to ISO string
        generated_at = row["generated_at"]
        if isinstance(generated_at, datetime):
            generated_at = generated_at.isoformat()
        
        return {
            "report_id": row["report_id"],
            "agent_config_id": row["agent_config_id"],
            "generated_at": generated_at,
            "report_json": report_json
        }

    def update_report_blocks(self, report_id: str, user_id: str, blocks: list) -> dict:
        """
        Actualiza el array de blocks en el report_json de un reporte existente.
        
        Args:
            report_id: ID del reporte a actualizar
            user_id: ID del usuario (para validar propiedad)
            blocks: Nuevo array de blocks que reemplazará el existente
            
        Returns:
            dict: Información de confirmación con report_id y cantidad de blocks
            
        Raises:
            ValueError: Si el reporte no existe o el usuario no es propietario
            RuntimeError: Si hay un error al actualizar
        """
        logger.info(f"🔄 [SERVICE] update_report_blocks IN: report_id={report_id}, user_id={user_id}, blocks_count={len(blocks)}")
        
        # Verificar que el reporte existe y pertenece al usuario
        query_check = f"""
        SELECT report_json, user_id
        FROM `{self.reports_table}`
        WHERE report_id = @report_id
        LIMIT 1
        """
        
        job_config_check = bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("report_id", "STRING", report_id)
        ])
        
        result = list(self.client.query(query_check, job_config=job_config_check).result())
        
        if not result:
            logger.warning(f"🔄 [SERVICE] update_report_blocks OUT: report not found")
            raise ValueError(f"No se encontró el reporte con ID: {report_id}")
        
        row = dict(result[0])
        
        # Validar que el usuario es propietario
        if row["user_id"] != user_id:
            logger.warning(f"🔄 [SERVICE] update_report_blocks OUT: user not authorized")
            raise ValueError(f"No tienes permiso para actualizar este reporte")
        
        # Obtener el report_json actual
        report_json = row["report_json"]
        if isinstance(report_json, str):
            try:
                report_json = json.loads(report_json)
            except json.JSONDecodeError:
                report_json = {}
        
        # Actualizar el array de blocks
        report_json["blocks"] = blocks
        
        # Actualizar en BigQuery
        query_update = f"""
        UPDATE `{self.reports_table}`
        SET report_json = @report_json,
            generated_at = @updated_at
        WHERE report_id = @report_id
        """
        
        job_config_update = bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("report_id", "STRING", report_id),
            bigquery.ScalarQueryParameter("report_json", "STRING", json.dumps(report_json, ensure_ascii=False)),
            bigquery.ScalarQueryParameter("updated_at", "TIMESTAMP", datetime.utcnow())
        ])
        
        try:
            query_job = self.client.query(query_update, job_config=job_config_update)
            query_job.result()
            
            logger.info(f"🔄 [SERVICE] update_report_blocks OUT: updated successfully, blocks_count={len(blocks)}")
            
            return {
                "message": "Blocks actualizados exitosamente",
                "report_id": report_id,
                "blocks_count": len(blocks)
            }
            
        except Exception as e:
            logger.error(f"🔄 [SERVICE] update_report_blocks OUT: error {e}")
            raise RuntimeError(f"Error al actualizar los blocks del reporte: {str(e)}")