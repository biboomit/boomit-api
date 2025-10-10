from typing import List, Optional
from google.cloud import bigquery
from app.core.exceptions import DatabaseConnectionError
from app.schemas.products import ProductResponse, ProductInternal
from datetime import datetime
from app.core.config import bigquery_config


class ProductService:
    def __init__(self):
        self.client = bigquery_config.get_client()
        self.table_id = bigquery_config.get_table_id("DIM_PRODUCTO")

    async def get_products(
        self, skip: int = 0, limit: int = 10, state: str = "all"
    ) -> tuple[List[ProductInternal], int]:
        """Obtener todos los productos con paginación"""
        state_mapping = {
            "active": "ACTIVO",
            "discontinued": "DESCONTINUADO",
        }
        base_query = f"""
        SELECT 
            producto_id,
            empresa_id,
            nombre_producto,
            categoria_producto,
            estado_producto,
            fecha_lanzamiento,
            fecha_fin,
            fecha_creacion,
            fecha_actualizacion
        FROM `{self.table_id}`
        """
        
        where_clause = ""
        query_params = []
        
        print("State parameter received:", state)
        
        if state.lower() in state_mapping:
            print("Filtering by state:", state)
            where_clause = "WHERE estado_producto = @estado"
            query_params.append(
                bigquery.ScalarQueryParameter("estado", "STRING", state_mapping[state.lower()])
            )
        elif state.lower() != "all":
            raise ValueError(
                f"Estado inválido: {state}. Debe ser 'all', 'active' o 'discontinued'"
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
            products = [ProductInternal(**dict(row)) for row in results]

            count_params = [p for p in query_params if p.name == "estado"]
            count_job_config = bigquery.QueryJobConfig(query_parameters=count_params)
            count_query_job = self.client.query(count_query, job_config=count_job_config)
            count_result = count_query_job.result()
            total_count = list(count_result)[0].total

            return products, total_count

        except Exception as e:
            raise DatabaseConnectionError(f"Error al obtener productos: {e}")


product_service = ProductService()