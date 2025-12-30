import json
import os
from datetime import datetime
from uuid import uuid4
from app.core.config import bigquery_config
from app.integrations.openai.report_generation_integration import OpenAIReportGenerationIntegration
from google.cloud import bigquery
from app.utils.pdf_generation import generate_pdf_from_json

class ReportGenerationService:

    def get_pdf_file(self, pdf_file_name: str) -> bytes:
        query = f"SELECT pdf_file_bytes FROM `{self.reports_table}` WHERE pdf_file_name = @pdf_file_name LIMIT 1"
        job_config = bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("pdf_file_name", "STRING", pdf_file_name)
        ])
        result = list(self.client.query(query, job_config=job_config).result())
        if not result:
            return None
        return result[0]["pdf_file_bytes"]
    
    def __init__(self):
        self.client = bigquery_config.get_client()
        self.agent_table = bigquery_config.get_table_id("DIM_AI_REPORT_AGENT_CONFIGS")
        self.reports_table = bigquery_config.get_table_id("AI_REPORTS_GENERATED")
        self.analytics_table = "takenos-bi.Dashboard.tabla_final"
        self.openai = OpenAIReportGenerationIntegration()

    def generate_report(self, agent_id: str, user_id: str) -> str:
        # 1. Consultar configuración del agente
        agent_config = self._get_agent_config(agent_id, user_id)
        # 2. Consultar datos analíticos
        analytics_data = self._get_analytics_data()
        # 3. Leer contratos de gráficos y reglas globales
        chart_data, global_rules = self._get_chart_contracts_and_rules()
        # 4. Llamar a OpenAI para generar el reporte
        report_json = self.openai.generate_report(
            analytics_data=analytics_data,
            agent_config=agent_config,
            chart_contracts=chart_data,
            global_rules=global_rules
        )
        # 5. Generar PDF real
        pdf_bytes = generate_pdf_from_json(report_json)
        pdf_file_name = f"report_{uuid4().hex}.pdf"
        self._save_report(agent_id, user_id, report_json, pdf_file_name, pdf_bytes)
        return pdf_file_name

    def _get_agent_config(self, agent_id, user_id):
        query = f"SELECT * FROM `{self.agent_table}` WHERE id = @agent_id AND user_id = @user_id LIMIT 1"
        job_config = bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("agent_id", "STRING", agent_id),
            bigquery.ScalarQueryParameter("user_id", "STRING", user_id)
        ])
        result = list(self.client.query(query, job_config=job_config).result())
        if not result:
            raise ValueError("No se encontró la configuración del agente.")
        return dict(result[0])

    def _get_analytics_data(self):
        # Solo las columnas requeridas
        # TODO: Agregar filtros de fechas
        query = f"""
        SELECT fecha, nombre_campana, Network, usuario_verificado, FCT, apertura_cuenta_exitosa, FTD, install, costo_total
        FROM `{self.analytics_table}`
        ORDER BY fecha DESC
        LIMIT 1000
        """
        result = self.client.query(query).result()
        return [dict(row) for row in result]

    def _get_chart_contracts_and_rules(self):
        base_path = os.path.join(os.path.dirname(__file__), "..", "core", "contracts", "char_contracts", "v1")
        with open(os.path.join(base_path, "index.json"), encoding="utf-8") as f:
            index = json.load(f)
        with open(os.path.join(base_path, index["global_rules_file"]), encoding="utf-8") as f:
            global_rules = json.load(f)

        # Cargar los contratos de cada bloque especificados en el index.json
        block_contracts = {}
        for block in index.get("blocks", []):
            block_name = block.get("name")
            contract_file = block.get("contract_file")
            if block_name and contract_file:
                contract_path = os.path.join(base_path, contract_file)
                try:
                    with open(contract_path, encoding="utf-8") as cf:
                        block_contracts[block_name] = json.load(cf)
                except Exception as e:
                    block_contracts[block_name] = {"error": f"No se pudo cargar el contrato: {str(e)}"}

        # Retornar el index, las reglas globales y los contratos de bloques
        return {"index": index, "block_contracts": block_contracts}, global_rules

    # _generate_pdf eliminado, ahora se usa generate_pdf_from_json

    def _save_report(self, agent_id, user_id, report_json, pdf_file_name, pdf_bytes):
        now = datetime.utcnow().isoformat()
        row = {
            "id": str(uuid4()),
            "agent_id": agent_id,
            "user_id": user_id,
            "report_json": json.dumps(report_json, ensure_ascii=False) if not isinstance(report_json, str) else report_json,
            "pdf_file_name": pdf_file_name,
            "pdf_file_bytes": pdf_bytes,
            "created_at": now,
            "updated_at": now
        }
        errors = self.client.insert_rows_json(self.reports_table, [row])
        if errors:
            raise RuntimeError(f"Error al guardar el reporte: {errors}")
