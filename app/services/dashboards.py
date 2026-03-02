from typing import List, Optional
from google.cloud import bigquery
from app.core.exceptions import DatabaseConnectionError
from app.schemas.dashboards import DashboardResponse, DashboardInternal, DashboardUpdateRequest, DashboardCreateRequest
from datetime import datetime
from app.core.config import bigquery_config


class DashboardService:
    def __init__(self):
        self.client = bigquery_config.get_client()
        self.table_id = bigquery_config.get_table_id("DIM_MAESTRO_DASH")

    async def get_dashboards(
        self,
        skip: int = 0,
        limit: int = 10,
        company_id: Optional[str] = None,
        product_id: Optional[str] = None,
    ) -> tuple[List[DashboardInternal], int]:
        """Obtener todos los dashboards con paginación"""
        base_query = """
        SELECT
            d.dash_id as dashboard_id,
            e.empresa_id as empresa_id,
            p.producto_id as producto_id,
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

        if product_id or company_id:
            where_conditions = []
            if company_id:
                where_conditions.append("e.empresa_id = @company_id")
                query_params.append(
                    bigquery.ScalarQueryParameter("company_id", "STRING", company_id)
                )
            if product_id:
                where_conditions.append("p.producto_id = @product_id")
                query_params.append(
                    bigquery.ScalarQueryParameter("product_id", "STRING", product_id)
                )
            if where_conditions:
                where_clause = "WHERE " + " AND ".join(where_conditions)

        count_query = f"""
        SELECT COUNT(*) as total
        FROM
            `marketing-dwh-specs.DWH.DIM_MAESTRO_DASH` d
        LEFT JOIN
            `marketing-dwh-specs.DWH.DIM_PRODUCTO` p
            ON d.producto_id = p.producto_id
        LEFT JOIN
            `marketing-dwh-specs.DWH.DIM_EMPRESA` e
            ON p.empresa_id = e.empresa_id
        {where_clause}
        """

        data_query = f"""
        {base_query}
        {where_clause}
        ORDER BY d.fecha_creacion DESC
        LIMIT @limit
        OFFSET @skip
        """

        try:
            count_job_config = bigquery.QueryJobConfig(query_parameters=query_params)
            count_job = self.client.query(count_query, job_config=count_job_config)
            count_result = list(count_job.result())
            total_count = count_result[0].total if count_result else 0

            data_params = query_params + [
                bigquery.ScalarQueryParameter("limit", "INT64", limit),
                bigquery.ScalarQueryParameter("skip", "INT64", skip),
            ]
            data_job_config = bigquery.QueryJobConfig(query_parameters=data_params)
            data_job = self.client.query(data_query, job_config=data_job_config)
            results = data_job.result()
            dashboards = [DashboardInternal(**dict(row)) for row in results]

            return dashboards, total_count
        except Exception as e:
            raise DatabaseConnectionError(details={"Dashboard service error": str(e)})

    async def get_dashboard_by_product_id(self, product_id: str) -> Optional[DashboardInternal]:
        """Obtener un dashboard por producto_id"""
        query = """
        SELECT
            d.dash_id as dashboard_id,
            e.empresa_id as empresa_id,
            p.producto_id as producto_id,
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
        WHERE p.producto_id = @product_id
        LIMIT 1
        """
        query_params = [
            bigquery.ScalarQueryParameter("product_id", "STRING", product_id)
        ]
        try:
            job_config = bigquery.QueryJobConfig(query_parameters=query_params)
            job = self.client.query(query, job_config=job_config)
            results = list(job.result())
            if not results:
                return None
            return DashboardInternal(**dict(results[0]))
        except Exception as e:
            raise DatabaseConnectionError(details={"Dashboard get by product_id error": str(e)})

    async def create_dashboard(self, payload: DashboardCreateRequest) -> int:
        """Crear un nuevo registro en DIM_MAESTRO_DASH"""
        now = datetime.utcnow()
        insert_query = """
        INSERT INTO `marketing-dwh-specs.DWH.DIM_MAESTRO_DASH`
            (dash_id, producto_id, url, url_embebido, Estado, fecha_creacion, fecha_actualizacion)
        VALUES
            (@dash_id, @producto_id, @url, @url_embebido, @estado, @fecha_creacion, @fecha_actualizacion)
        """
        query_params = [
            bigquery.ScalarQueryParameter("dash_id", "STRING", payload.dash_id),
            bigquery.ScalarQueryParameter("producto_id", "STRING", payload.producto_id),
            bigquery.ScalarQueryParameter("url", "STRING", payload.url),
            bigquery.ScalarQueryParameter("url_embebido", "STRING", payload.url_embebido),
            bigquery.ScalarQueryParameter("estado", "STRING", payload.estado),
            bigquery.ScalarQueryParameter("fecha_creacion", "TIMESTAMP", now),
            bigquery.ScalarQueryParameter("fecha_actualizacion", "TIMESTAMP", now),
        ]
        try:
            job_config = bigquery.QueryJobConfig(query_parameters=query_params)
            job = self.client.query(insert_query, job_config=job_config)
            job.result()
            return job.num_dml_affected_rows or 0
        except Exception as e:
            raise DatabaseConnectionError(details={"Dashboard create error": str(e)})

    async def update_dashboard(self, producto_id: str, payload: DashboardUpdateRequest) -> int:
        """Actualizar url y/o url_embebido de un dashboard por producto_id"""
        if payload.url is None and payload.url_embebido is None:
            return 0

        set_clauses = []
        query_params = []

        if payload.url is not None:
            set_clauses.append("url = @url")
            query_params.append(bigquery.ScalarQueryParameter("url", "STRING", payload.url))

        if payload.url_embebido is not None:
            set_clauses.append("url_embebido = @url_embebido")
            query_params.append(bigquery.ScalarQueryParameter("url_embebido", "STRING", payload.url_embebido))

        set_clauses.append("fecha_actualizacion = @fecha_actualizacion")
        query_params.append(
            bigquery.ScalarQueryParameter("fecha_actualizacion", "TIMESTAMP", datetime.utcnow())
        )
        query_params.append(bigquery.ScalarQueryParameter("producto_id", "STRING", producto_id))

        update_query = f"""
        UPDATE `marketing-dwh-specs.DWH.DIM_MAESTRO_DASH`
        SET {', '.join(set_clauses)}
        WHERE producto_id = @producto_id
        """

        try:
            job_config = bigquery.QueryJobConfig(query_parameters=query_params)
            job = self.client.query(update_query, job_config=job_config)
            job.result()
            return job.num_dml_affected_rows or 0
        except Exception as e:
            raise DatabaseConnectionError(details={"Dashboard update error": str(e)})


dashboard_service = DashboardService()
