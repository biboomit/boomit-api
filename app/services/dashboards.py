from typing import List, Optional
from app.core.exceptions import DatabaseConnectionError
from app.schemas.dashboards import DashboardResponse, DashboardInternal
from datetime import datetime
from app.core.config import bigquery_config


class DashboardService:
    def __init__(self):
        self.client = bigquery_config.get_client()
        self.table_id = bigquery_config.get_table_id("DIM_MAESTRO_DASH")

    async def get_dashboards(
        self, skip: int = 0, limit: int = 10
    ) -> tuple[List[DashboardInternal], int]:
        """Obtener todos los dashboards con paginación"""
        query = f"""
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
        LIMIT {limit}
        OFFSET {skip};
        """

        try:
            query_job = self.client.query(query)
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
