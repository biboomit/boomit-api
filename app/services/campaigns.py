from typing import List, Optional
from google.cloud import bigquery
from app.core.exceptions import DatabaseConnectionError
from app.schemas.campaigns import CampaignResponse, CampaignInternal
from datetime import datetime
from app.core.config import bigquery_config


class CampaignService:
    def __init__(self):
        self.client = bigquery_config.get_client()
        self.table_id = bigquery_config.get_table_id("DIM_CAMPANA")

    async def get_campaigns(
        self, skip: int = 0, limit: int = 10, state: str = "all"
    ) -> tuple[List[CampaignInternal], int]:
        """Obtener todas las campañas con paginación"""
        state_mapping = {
            "active": "ACTIVA",
            "paused": "INACTIVA",
        }
        base_query = f"""
        SELECT 
            campana_id,
            network_id,
            empresa_id,
            producto_id,
            canal_id,
            nombre_campana,
            objetivo_campana,
            tipo_campana,
            fecha_primer_inicio,
            fecha_ultimo_apagado,
            estado_campana,
            fecha_creacion,
            fecha_actualizacion
        FROM `{self.table_id}`
        """

        where_clause = ""
        query_params = []

        if state.lower() in state_mapping:
            where_clause = "WHERE estado_campana = @estado"
            query_params.append(
                bigquery.ScalarQueryParameter("estado", "STRING", state_mapping[state.lower()])
            )
        elif state.lower() != "all":
            raise ValueError(
                f"Estado inválido: {state}. Debe ser 'all', 'active' o 'paused'"
            )

        data_query = f"""
        {base_query}
        {where_clause}
        ORDER BY fecha_creacion DESC
        LIMIT @limit
        OFFSET @skip
        """

        query_params.extend([
            bigquery.ScalarQueryParameter("limit", "INT64", limit),
            bigquery.ScalarQueryParameter("skip", "INT64", skip)
        ])

        count_query = f"""
        SELECT COUNT(*) as total
        FROM `{self.table_id}`
        {where_clause}
        """

        try:
            job_config = bigquery.QueryJobConfig(query_parameters=query_params)
            query_job = self.client.query(data_query, job_config=job_config)
            results = query_job.result()
            campaigns = [CampaignInternal(**dict(row)) for row in results]

            # Para el count, solo usar el parámetro de estado si existe
            count_params = [p for p in query_params if p.name == "estado"]
            count_job_config = bigquery.QueryJobConfig(query_parameters=count_params) if count_params else None
            count_job = self.client.query(count_query, job_config=count_job_config)
            count_result = count_job.result()
            total_count = list(count_result)[0].total

            return campaigns, total_count

        except Exception as e:
            raise DatabaseConnectionError(details={"Campaign service error": str(e)})


campaign_service = CampaignService()
