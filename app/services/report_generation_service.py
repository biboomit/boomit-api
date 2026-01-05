import json
import os
from datetime import datetime, timedelta
from uuid import uuid4
from app.core.config import bigquery_config
from app.integrations.openai.report_generation_integration import OpenAIReportGenerationIntegration
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
        self.openai = OpenAIReportGenerationIntegration()

    def generate_report(self, agent_id: str, user_id: str, date_from: str = None, date_to: str = None) -> str:
        logger.info(f"📝 [SERVICE] generate_report IN: agent_id={agent_id}, user_id={user_id}")
        # 1. Consultar configuración del agente
        agent_config = self._get_agent_config(agent_id, user_id)
        # 2. Consultar datos analíticos y calcular data_window
        analytics_data, data_window = self._get_analytics_data_with_window(date_from=date_from, date_to=date_to)
        # 3. Leer contratos de gráficos y reglas globales
        chart_data, global_rules = self._get_chart_contracts_and_rules()

        # 4. Llamar a OpenAI para generar el reporte, pasando data_window (comentado temporalmente)
        report_json = self.openai.generate_report(
            analytics_data=analytics_data,
            agent_config=agent_config,
            chart_contracts=chart_data,
            global_rules=global_rules,
            data_window=data_window
        )
                
        # Loguea el resultado crudo de OpenAI antes de cualquier acceso/cast
        logger.info(f"[OPENAI RAW RESULT] type={type(report_json)}, value={str(report_json)[:1000]}")
        if not isinstance(report_json, dict):
            logger.error(f"[OPENAI ERROR] El resultado de OpenAI no es un dict: {type(report_json)}: {str(report_json)[:1000]}")
            raise RuntimeError(f"El resultado de OpenAI no es un dict: {type(report_json)}: {str(report_json)[:1000]}")

        # Para pruebas: solo retorna la cantidad de registros y el data_window
        logger.info(f"[PRUEBA] analytics_data: {len(analytics_data)} registros, data_window: {data_window}")
        logger.debug(f"[PRUEBA] chart_data: {json.dumps(chart_data, ensure_ascii=False)}")
        logger.debug(f"[PRUEBA] global_rules: {json.dumps(global_rules, ensure_ascii=False)}")
        logger.info(f"📝 [SERVICE] generate_report OUT: OK")

        # 5. Guardar el reporte generado
        self._save_report(agent_id, user_id, report_json)

        # 6. Retornar mensaje de exito
        return f"Successfully generated report structure for agent_id: {agent_id}, user_id: {user_id}"

    def _get_agent_config(self, agent_id, user_id):
        logger.info(f"🔍 [SERVICE] _get_agent_config IN: agent_id={agent_id}, user_id={user_id}")
        query = f"SELECT * FROM `{self.agent_table}` WHERE id = @agent_id AND user_id = @user_id LIMIT 1"
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

    def _get_analytics_data_with_window(self, date_from: str = None, date_to: str = None):
        logger.info(f"📊 [SERVICE] _get_analytics_data_with_window IN (date_from={date_from}, date_to={date_to})")
        # Construir la URL con los parámetros de fecha si se proporcionan
        base_url = os.getenv("ANALYTICS_SERVICE_URL", "https://takenos-dashboard-data-715418856987.us-central1.run.app/analytics/csv?limit=10")
        from urllib.parse import urlencode, urlparse, parse_qs, urlunparse
        url_parts = list(urlparse(base_url))
        query = parse_qs(url_parts[4])
        if date_from:
            query["date_from"] = [date_from]
        if date_to:
            query["date_to"] = [date_to]
        # Aplanar los valores para urlencode
        query = {k: v[0] if isinstance(v, list) and len(v) == 1 else v for k, v in query.items()}
        url_parts[4] = urlencode(query)
        final_url = urlunparse(url_parts)
        logger.info(f"[SERVICE] Llamando a microservicio con URL: {final_url}")
        response = requests.get(final_url)
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
        row = {
            "report_id": str(uuid4()),
            "agent_config_id": agent_id,
            "user_id": user_id,
            "report_json": json.dumps(report_json, ensure_ascii=False) if not isinstance(report_json, str) else report_json,
            "generated_at": now
        }
        errors = self.client.insert_rows_json(self.reports_table, [row])
        if errors:
            logger.error(f"💾 [SERVICE] _save_report OUT: error {errors}")
            raise RuntimeError(f"Error al guardar el reporte: {errors}")
        logger.info(f"💾 [SERVICE] _save_report OUT: guardado exitosamente para agent_id: {agent_id}, user_id: {user_id}")