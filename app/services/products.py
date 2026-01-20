from typing import List, Optional
from google.cloud import bigquery
from app.core.exceptions import DatabaseConnectionError
from app.schemas.products import ProductResponse, ProductInternal, ProductCreateRequest, ProductUpdateRequest
from datetime import datetime
from app.core.config import bigquery_config
import uuid


class ProductService:
    def __init__(self):
        self.client = bigquery_config.get_client()
        self.table_id = bigquery_config.get_table_id("DIM_PRODUCTO")

    async def get_products(
        self, skip: int = 0, limit: int = 10, state: str = "all", company_id: Optional[str] = None
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
        
        if company_id or state.lower() != "all":
            where_conditions = []
            if state.lower() in state_mapping:
                where_conditions.append("estado_producto = @estado")
                query_params.append(
                    bigquery.ScalarQueryParameter("estado", "STRING", state_mapping[state.lower()])
                )
            if company_id:
                where_conditions.append("empresa_id = @empresa_id")
                query_params.append(
                    bigquery.ScalarQueryParameter("empresa_id", "STRING", company_id)
                )
            if where_conditions:
                where_clause = "WHERE " + " AND ".join(where_conditions)
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

            count_params = [p for p in query_params if p.name in ("estado", "empresa_id")]
            count_job_config = bigquery.QueryJobConfig(query_parameters=count_params)
            count_query_job = self.client.query(count_query, job_config=count_job_config)
            count_result = count_query_job.result()
            total_count = list(count_result)[0].total

            return products, total_count

        except Exception as e:
            raise DatabaseConnectionError(f"Error al obtener productos: {e}")

    async def get_product_by_id(self, producto_id: str) -> Optional[ProductInternal]:
        """Obtener un producto por su ID"""
        query = f"""
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
        WHERE producto_id = @producto_id
        """

        query_params = [
            bigquery.ScalarQueryParameter("producto_id", "STRING", producto_id)
        ]

        try:
            job_config = bigquery.QueryJobConfig(query_parameters=query_params)
            query_job = self.client.query(query, job_config=job_config)
            results = query_job.result()
            
            rows = list(results)
            if not rows:
                return None
            
            return ProductInternal(**dict(rows[0]))

        except Exception as e:
            raise DatabaseConnectionError(f"Error al obtener producto: {e}")

    async def create_product(self, product_data: ProductCreateRequest) -> ProductInternal:
        """Crear un nuevo producto"""
        producto_id = f"pr{str(uuid.uuid4())[:8]}"
        now = datetime.utcnow()

        query = f"""
        INSERT INTO `{self.table_id}` (
            producto_id,
            empresa_id,
            nombre_producto,
            categoria_producto,
            estado_producto,
            fecha_lanzamiento,
            fecha_fin,
            fecha_creacion,
            fecha_actualizacion
        ) VALUES (
            @producto_id,
            @empresa_id,
            @nombre_producto,
            @categoria_producto,
            @estado_producto,
            @fecha_lanzamiento,
            @fecha_fin,
            @fecha_creacion,
            @fecha_actualizacion
        )
        """

        query_params = [
            bigquery.ScalarQueryParameter("producto_id", "STRING", producto_id),
            bigquery.ScalarQueryParameter("empresa_id", "STRING", product_data.empresa_id),
            bigquery.ScalarQueryParameter("nombre_producto", "STRING", product_data.nombre_producto),
            bigquery.ScalarQueryParameter("categoria_producto", "STRING", product_data.categoria_producto),
            bigquery.ScalarQueryParameter("estado_producto", "STRING", product_data.estado_producto),
            bigquery.ScalarQueryParameter("fecha_lanzamiento", "DATE", product_data.fecha_lanzamiento.date() if product_data.fecha_lanzamiento else None),
            bigquery.ScalarQueryParameter("fecha_fin", "DATE", product_data.fecha_fin.date() if product_data.fecha_fin else None),
            bigquery.ScalarQueryParameter("fecha_creacion", "TIMESTAMP", now),
            bigquery.ScalarQueryParameter("fecha_actualizacion", "TIMESTAMP", now)
        ]

        try:
            job_config = bigquery.QueryJobConfig(query_parameters=query_params)
            query_job = self.client.query(query, job_config=job_config)
            query_job.result()

            # Retrieve the created product
            created_product = await self.get_product_by_id(producto_id)
            if not created_product:
                raise DatabaseConnectionError("Error al recuperar el producto creado")
            
            return created_product

        except Exception as e:
            raise DatabaseConnectionError(f"Error al crear producto: {e}")

    async def update_product(self, producto_id: str, product_data: ProductUpdateRequest) -> Optional[ProductInternal]:
        """Actualizar un producto existente"""
        # First check if product exists
        existing_product = await self.get_product_by_id(producto_id)
        if not existing_product:
            return None

        # Build dynamic update query based on provided fields
        update_fields = []
        query_params = [
            bigquery.ScalarQueryParameter("producto_id", "STRING", producto_id),
            bigquery.ScalarQueryParameter("fecha_actualizacion", "TIMESTAMP", datetime.utcnow())
        ]

        if product_data.empresa_id is not None:
            update_fields.append("empresa_id = @empresa_id")
            query_params.append(bigquery.ScalarQueryParameter("empresa_id", "STRING", product_data.empresa_id))
        
        if product_data.nombre_producto is not None:
            update_fields.append("nombre_producto = @nombre_producto")
            query_params.append(bigquery.ScalarQueryParameter("nombre_producto", "STRING", product_data.nombre_producto))
        
        if product_data.categoria_producto is not None:
            update_fields.append("categoria_producto = @categoria_producto")
            query_params.append(bigquery.ScalarQueryParameter("categoria_producto", "STRING", product_data.categoria_producto))
        
        if product_data.estado_producto is not None:
            update_fields.append("estado_producto = @estado_producto")
            query_params.append(bigquery.ScalarQueryParameter("estado_producto", "STRING", product_data.estado_producto))
        
        if product_data.fecha_lanzamiento is not None:
            update_fields.append("fecha_lanzamiento = @fecha_lanzamiento")
            query_params.append(bigquery.ScalarQueryParameter("fecha_lanzamiento", "DATE", product_data.fecha_lanzamiento.date()))
        
        if product_data.fecha_fin is not None:
            update_fields.append("fecha_fin = @fecha_fin")
            query_params.append(bigquery.ScalarQueryParameter("fecha_fin", "DATE", product_data.fecha_fin.date()))

        # Always update fecha_actualizacion
        update_fields.append("fecha_actualizacion = @fecha_actualizacion")

        if not update_fields:
            return existing_product

        query = f"""
        UPDATE `{self.table_id}`
        SET {', '.join(update_fields)}
        WHERE producto_id = @producto_id
        """

        try:
            job_config = bigquery.QueryJobConfig(query_parameters=query_params)
            query_job = self.client.query(query, job_config=job_config)
            query_job.result()

            # Retrieve the updated product
            updated_product = await self.get_product_by_id(producto_id)
            return updated_product

        except Exception as e:
            raise DatabaseConnectionError(f"Error al actualizar producto: {e}")


product_service = ProductService()