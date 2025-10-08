from typing import List, Optional
from google.cloud import bigquery
from app.core.exceptions import DatabaseConnectionError
from app.schemas.dashboards import DashboardResponse, DashboardInternal
from datetime import datetime
from app.core.config import bigquery_config


class DashboardService:
    def __init__(self):
        self.client = bigquery_config.get_client()
        self.table_id = bigquery_config.get_table_id("DIM_MAESTRO_DASH")

    async def get_dashboards(
        self, skip: int = 0, limit: int = 10, company_id: Optional[str] = None
    ) -> tuple[List[DashboardInternal], int]:
        """Obtener todos los dashboards con paginación"""
        base_query = """
        SELECT
            d.dash_id as dashboard_id,
            e.empresa_id as empresa_id,
            p.nombre_producto as nombre_dashboard,
            e.nombre_empresa as nombre_empresa,
            d.url,
            d.url_embebido as embed_url,
            d.Estado as estado,
            d.fecha_creacion,
            d.fecha_actualizacion
        FROM
            `marketing-dwh-specs.DWH.DIM_MAESTRO_DASH` d
        LEFT JOIN
            `marketing-dwh-specs.DWH.DIM_PRODUCTO` p
            ON d.producto_id = p.producto_id
        LEFT JOIN
            `marketing-dwh-specs.DWH.DIM_EMPRESA` e
            ON p.empresa_id = e.empresa_id
        """

        where_clause = ""
        query_params = []

        if company_id:
            where_clause = "WHERE e.empresa_id = @company_id"
            query_params.append(
                bigquery.ScalarQueryParameter("company_id", "STRING", company_id)
            )

        query = f"""
        {base_query}
        {where_clause}
        ORDER BY d.fecha_creacion DESC
        LIMIT @limit
        OFFSET @skip
        """

        query_params.extend(
            [
                bigquery.ScalarQueryParameter("limit", "INT64", limit),
                bigquery.ScalarQueryParameter("skip", "INT64", skip),
            ]
        )

        job_config = bigquery.QueryJobConfig(query_parameters=query_params)

        try:
            query_job = self.client.query(query, job_config=job_config)
            results = query_job.result()
            dashboards = [DashboardInternal(**dict(row)) for row in results]

            count_query = f"SELECT COUNT(*) as total FROM `{self.table_id}`"
            count_job = self.client.query(count_query)
            count_result = count_job.result()
            total_count = list(count_result)[0].total

            return dashboards, total_count
        except Exception as e:
            raise DatabaseConnectionError(details={"Dashboard service error": str(e)})


dashboard_service = DashboardService()
