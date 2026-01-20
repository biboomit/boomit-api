import json
import os
from datetime import datetime, timedelta
from uuid import uuid4
from app.core.config import bigquery_config
from app.integrations.openai.report_generation_integration import OpenAIReportGenerationIntegration
from app.integrations.gcp.identity_token_client import GCPIdentityTokenClient
from google.cloud import bigquery
import logging
import requests
import csv
from io import StringIO

logger = logging.getLogger(__name__)

class ReportGenerationService:
    
    def __init__(self):
        logger.info("🚀 [SERVICE] ReportGenerationService INIT")
        self.client = bigquery_config.get_client()
        self.agent_table = bigquery_config.get_table_id("DIM_AI_REPORT_AGENT_CONFIGS")
        self.reports_table = bigquery_config.get_table_id_with_dataset(
            "AIOutput", "AI_MARKETING_REPORTS")
        self.analytics_table = bigquery_config.get_table_id_with_dataset("takenos-bi", "Dashboard.tabla_final")
        self.analytics_service_base_url = os.getenv(
            "ANALYTICS_SERVICE_URL",
            "https://takenos-dashboard-data-715418856987.us-central1.run.app",
        )
        self.report_service_url = os.getenv(
            "REPORT_SERVICE_URL",
            "https://boomit-report-715418856987.us-central1.run.app",
        )
        self.openai = OpenAIReportGenerationIntegration()
        self.gcp_auth_client = GCPIdentityTokenClient()

    def generate_report(self, agent_id: str, user_id: str, date_from: str = None, date_to: str = None, top_n: int = 10) -> str:
        logger.info(f"📝 [SERVICE] generate_report IN: agent_id={agent_id}, user_id={user_id}, top_n={top_n}")
        # 1. Consultar configuración del agente
        agent_config = self._get_agent_config(agent_id, user_id)
        # 2. Consultar datos analíticos y calcular data_window
        analytics_data, data_window = self._get_analytics_data_with_window(date_from=date_from, date_to=date_to, top_n=top_n)
        # 3. Leer contratos de gráficos y reglas globales
        chart_data, global_rules = self._get_chart_contracts_and_rules()

        # 4. Llamar a OpenAI para generar el reporte, pasando data_window
        report_json = self.openai.generate_report(
            analytics_data=analytics_data,
            agent_config=agent_config,
            chart_contracts=chart_data,
            global_rules=global_rules,
            data_window=data_window
        )

        if not isinstance(report_json, dict):
            logger.error(f"[OPENAI ERROR] El resultado de OpenAI no es un dict: {type(report_json)}: {str(report_json)[:1000]}")
            raise RuntimeError(f"El resultado de OpenAI no es un dict: {type(report_json)}: {str(report_json)[:1000]}")

        # 5. Guardar el reporte generado y retornar el ID
        report_id = self._save_report(agent_id, user_id, report_json)

        # 6. Retornar mensaje de exito y report_id
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

    def _get_analytics_data_with_window(self, date_from: str = None, date_to: str = None, top_n: int = 10):
        logger.info(f"📊 [SERVICE] _get_analytics_data_with_window IN (date_from={date_from}, date_to={date_to}, top_n={top_n}) from Takenos microservice")
        # Construir la URL sin reutilizar query previa (evita duplicar /analytics/csv con params)
        from urllib.parse import urlencode, urlparse, urlunparse

        base_raw = (self.analytics_service_base_url or "").strip()
        parsed = urlparse(base_raw)

        # Si no viene esquema/host en la variable, es una configuración inválida
        if not parsed.netloc:
            raise RuntimeError("ANALYTICS_SERVICE_URL debe incluir esquema y host, por ej. https://takenos-dashboard-data-...")

        # Conservar el path si ya viene definido; si no, usar el endpoint por defecto
        path = parsed.path or "/analytics/csv"

        # Usar un query limpio, sin arrastrar el existente
        query_params = {"top_n": str(top_n)}
        if date_from:
            query_params["date_from"] = date_from
        if date_to:
            query_params["date_to"] = date_to

        final_url = urlunparse((parsed.scheme, parsed.netloc, path, "", urlencode(query_params), ""))
        logger.info(f"[SERVICE] Llamando a microservicio con URL: {final_url}")
        
        # Para despliegues locales/servicio interno no requerimos token de identidad
        headers = {}
        if parsed.scheme == "https":
            headers = self.gcp_auth_client.get_authorized_headers(self.analytics_service_base_url)
        
        response = requests.get(final_url, headers=headers)
        if response.status_code != 200:
            logger.error(f"Error al obtener datos analíticos: {response.status_code} {response.text}")
            raise RuntimeError("No se pudo obtener datos analíticos del microservicio externo")
        # Leer data_window del header
        data_window = json.loads(response.headers.get("X-Data-Window", "{}"))
        # Parsear CSV
        try:
            logger.info(f"[CSV DEBUG] Decodificando respuesta CSV, tamaño: {len(response.content)} bytes")
            csv_content = response.content.decode("utf-8")
            logger.info(f"[CSV DEBUG] Primeros 200 caracteres del CSV: {csv_content[:200]}")
            reader = csv.DictReader(StringIO(csv_content))
            logger.info(f"[CSV DEBUG] DictReader creado, fieldnames: {reader.fieldnames}")
        except Exception as e:
            logger.error(f"[CSV ERROR] Error al preparar DictReader: {e}")
            raise
        analytics_data = []
        for idx, row in enumerate(reader):
            logger.debug(f"[CSV DEBUG] Row {idx}: type={type(row)}, value={row}")
            if isinstance(row, dict) and any(row.values()):
                analytics_data.append(row)
            else:
                logger.warning(f"[CSV WARNING] Skipping row {idx}: type={type(row)}, value={row}")
        logger.info(f"Datos analíticos obtenidos del microservicio: {len(analytics_data)} registros")
        logger.info("📊 [SERVICE] _get_analytics_data_with_window OUT")
        return analytics_data, {"data_window": data_window}

    def _get_chart_contracts_and_rules(self):
        logger.info("📈 [SERVICE] _get_chart_contracts_and_rules IN")
        try:
            base_path = os.path.join(os.path.dirname(__file__), "..", "core", "contracts", "char_contracts", "v1")
            index_path = os.path.join(base_path, "index.json")
            logger.info(f"[CONTRACTS DEBUG] Leyendo index.json en: {index_path}")
            with open(index_path, encoding="utf-8") as f:
                index = json.load(f)
            global_rules_path = os.path.join(base_path, index["global_rules_file"])
            logger.info(f"[CONTRACTS DEBUG] Leyendo global_rules en: {global_rules_path}")
            with open(global_rules_path, encoding="utf-8") as f:
                global_rules = json.load(f)

            # Cargar los contratos de cada bloque especificados en el index.json
            block_contracts = {}
            for block in index.get("blocks", []):
                block_name = block.get("name")
                contract_file = block.get("contract_file")
                if block_name and contract_file:
                    contract_path = os.path.join(base_path, contract_file)
                    try:
                        logger.info(f"[CONTRACTS DEBUG] Leyendo contrato {block_name} en: {contract_path}")
                        with open(contract_path, encoding="utf-8") as cf:
                            block_contracts[block_name] = json.load(cf)
                    except Exception as e:
                        logger.error(f"[CONTRACTS ERROR] No se pudo cargar el contrato {block_name}: {e}")
                        block_contracts[block_name] = {"error": f"No se pudo cargar el contrato: {str(e)}"}

            logger.info("📈 [SERVICE] _get_chart_contracts_and_rules OUT: contratos y reglas cargados exitosamente")
            return {"index": index, "block_contracts": block_contracts}, global_rules
        except Exception as e:
            logger.error(f"[CONTRACTS ERROR] Error crítico al cargar contratos o reglas: {e}")
            raise

    def _save_report(self, agent_id, user_id, report_json):
        logger.info(f"💾 [SERVICE] _save_report IN: agent_id={agent_id}, user_id={user_id}")
        now = datetime.utcnow().isoformat()
        report_id = str(uuid4())
        row = {
            "report_id": report_id,
            "agent_config_id": agent_id,
            "user_id": user_id,
            "report_json": json.dumps(report_json, ensure_ascii=False) if not isinstance(report_json, str) else report_json,
            "generated_at": now
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

    def get_report_html(self, report_id: str) -> str:
        """
        Obtiene el HTML renderizado de un reporte desde el servicio de boomit-report.
        
        Args:
            report_id: ID del reporte a obtener
            
        Returns:
            str: HTML del reporte renderizado
            
        Raises:
            ValueError: Si el reporte no existe
            RuntimeError: Si hay un error al obtener el reporte
        """
        logger.info(f"📝 [SERVICE] get_report_html IN: report_id={report_id}")
        
        # URL del servicio de boomit-report en GCP
        report_url = f"{self.report_service_url}/reports/{report_id}/html"
        
        # Obtener headers con token de identidad para Cloud Run
        headers = self.gcp_auth_client.get_authorized_headers(self.report_service_url)
        
        logger.info(f"[SERVICE] Llamando al servicio de reportes: {report_url}")
        
        try:
            response = requests.get(report_url, headers=headers, timeout=30)
            
            if response.status_code == 404:
                logger.warning(f"[SERVICE] Reporte no encontrado: {report_id}")
                raise ValueError(f"Reporte con ID {report_id} no encontrado")
            
            if response.status_code != 200:
                logger.error(f"[SERVICE] Error al obtener reporte: {response.status_code} {response.text}")
                raise RuntimeError(f"Error al obtener el reporte: {response.status_code}")
            
            logger.info(f"📝 [SERVICE] get_report_html OUT: HTML obtenido exitosamente")
            return response.text
            
        except requests.exceptions.Timeout:
            logger.error(f"[SERVICE] Timeout al obtener el reporte {report_id}")
            raise RuntimeError("Timeout al obtener el reporte del servicio")
        except requests.exceptions.RequestException as e:
            logger.error(f"[SERVICE] Error de conexión al obtener el reporte: {e}")
            raise RuntimeError(f"Error de conexión con el servicio de reportes: {str(e)}")

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