from typing import List, Optional
from google.cloud import bigquery
from app.core.exceptions import DatabaseConnectionError
from app.schemas.companies import CompanyResponse, CompanyInternal, CompanyCreateRequest, CompanyUpdateRequest
from datetime import datetime
from app.core.config import bigquery_config
import uuid


class CompanyService:
    def __init__(self):
        self.client = bigquery_config.get_client()
        self.table_id = bigquery_config.get_table_id("DIM_EMPRESA")

    async def get_companies(
        self, skip: int = 0, limit: int = 10
    ) -> tuple[List[CompanyInternal], int]:
        """Obtener todas las empresas con paginación"""
        query = f"""
        SELECT 
            empresa_id,
            nombre_empresa,
            pais,
            industria,
            fecha_inicio_relacion,
            fecha_fin_relacion,
            estado_empresa,
            motivo_cierre,
            fecha_creacion,
            fecha_actualizacion
        FROM `{self.table_id}`
        ORDER BY fecha_creacion DESC
        LIMIT @limit
        OFFSET @skip
        """

        query_params = [
            bigquery.ScalarQueryParameter("limit", "INT64", limit),
            bigquery.ScalarQueryParameter("skip", "INT64", skip)
        ]

        count_query = f"SELECT COUNT(*) as total FROM `{self.table_id}`"

        try:
            job_config = bigquery.QueryJobConfig(query_parameters=query_params)
            query_job = self.client.query(query, job_config=job_config)
            results = query_job.result()
            companies = [CompanyInternal(**dict(row)) for row in results]

            count_job = self.client.query(count_query)
            count_result = count_job.result()
            total_count = list(count_result)[0].total

            return companies, total_count

        except Exception as e:
            raise DatabaseConnectionError(details={"Company service error": str(e)})

    async def get_company_by_id(self, empresa_id: str) -> Optional[CompanyInternal]:
        """Obtener una empresa por su ID"""
        query = f"""
        SELECT 
            empresa_id,
            nombre_empresa,
            pais,
            industria,
            fecha_inicio_relacion,
            fecha_fin_relacion,
            estado_empresa,
            motivo_cierre,
            fecha_creacion,
            fecha_actualizacion
        FROM `{self.table_id}`
        WHERE empresa_id = @empresa_id
        """

        query_params = [
            bigquery.ScalarQueryParameter("empresa_id", "STRING", empresa_id)
        ]

        try:
            job_config = bigquery.QueryJobConfig(query_parameters=query_params)
            query_job = self.client.query(query, job_config=job_config)
            results = query_job.result()
            
            rows = list(results)
            if not rows:
                return None
            
            return CompanyInternal(**dict(rows[0]))

        except Exception as e:
            raise DatabaseConnectionError(details={"Company service error": str(e)})

    async def create_company(self, company_data: CompanyCreateRequest) -> CompanyInternal:
        """Crear una nueva empresa"""
        empresa_id = f"ee{str(uuid.uuid4())[:8]}"
        now = datetime.utcnow()

        query = f"""
        INSERT INTO `{self.table_id}` (
            empresa_id,
            nombre_empresa,
            pais,
            industria,
            fecha_inicio_relacion,
            fecha_fin_relacion,
            estado_empresa,
            motivo_cierre,
            fecha_creacion,
            fecha_actualizacion
        ) VALUES (
            @empresa_id,
            @nombre_empresa,
            @pais,
            @industria,
            @fecha_inicio_relacion,
            @fecha_fin_relacion,
            @estado_empresa,
            @motivo_cierre,
            @fecha_creacion,
            @fecha_actualizacion
        )
        """

        query_params = [
            bigquery.ScalarQueryParameter("empresa_id", "STRING", empresa_id),
            bigquery.ScalarQueryParameter("nombre_empresa", "STRING", company_data.nombre_empresa),
            bigquery.ScalarQueryParameter("pais", "STRING", company_data.pais),
            bigquery.ScalarQueryParameter("industria", "STRING", company_data.industria),
            bigquery.ScalarQueryParameter("fecha_inicio_relacion", "DATE", company_data.fecha_inicio_relacion.date() if company_data.fecha_inicio_relacion else None),
            bigquery.ScalarQueryParameter("fecha_fin_relacion", "DATE", company_data.fecha_fin_relacion.date() if company_data.fecha_fin_relacion else None),
            bigquery.ScalarQueryParameter("estado_empresa", "STRING", company_data.estado_empresa),
            bigquery.ScalarQueryParameter("motivo_cierre", "STRING", company_data.motivo_cierre),
            bigquery.ScalarQueryParameter("fecha_creacion", "TIMESTAMP", now),
            bigquery.ScalarQueryParameter("fecha_actualizacion", "TIMESTAMP", now)
        ]

        try:
            job_config = bigquery.QueryJobConfig(query_parameters=query_params)
            query_job = self.client.query(query, job_config=job_config)
            query_job.result()

            # Retrieve the created company
            created_company = await self.get_company_by_id(empresa_id)
            if not created_company:
                raise DatabaseConnectionError(details={"Company service error": "Failed to retrieve created company"})
            
            return created_company

        except Exception as e:
            raise DatabaseConnectionError(details={"Company service error": str(e)})

    async def update_company(self, empresa_id: str, company_data: CompanyUpdateRequest) -> Optional[CompanyInternal]:
        """Actualizar una empresa existente"""
        # First check if company exists
        existing_company = await self.get_company_by_id(empresa_id)
        if not existing_company:
            return None

        # Build dynamic update query based on provided fields
        update_fields = []
        query_params = [
            bigquery.ScalarQueryParameter("empresa_id", "STRING", empresa_id),
            bigquery.ScalarQueryParameter("fecha_actualizacion", "TIMESTAMP", datetime.utcnow())
        ]

        if company_data.nombre_empresa is not None:
            update_fields.append("nombre_empresa = @nombre_empresa")
            query_params.append(bigquery.ScalarQueryParameter("nombre_empresa", "STRING", company_data.nombre_empresa))
        
        if company_data.pais is not None:
            update_fields.append("pais = @pais")
            query_params.append(bigquery.ScalarQueryParameter("pais", "STRING", company_data.pais))
        
        if company_data.industria is not None:
            update_fields.append("industria = @industria")
            query_params.append(bigquery.ScalarQueryParameter("industria", "STRING", company_data.industria))
        
        if company_data.fecha_inicio_relacion is not None:
            update_fields.append("fecha_inicio_relacion = @fecha_inicio_relacion")
            query_params.append(bigquery.ScalarQueryParameter("fecha_inicio_relacion", "DATE", company_data.fecha_inicio_relacion.date()))
        
        if company_data.fecha_fin_relacion is not None:
            update_fields.append("fecha_fin_relacion = @fecha_fin_relacion")
            query_params.append(bigquery.ScalarQueryParameter("fecha_fin_relacion", "DATE", company_data.fecha_fin_relacion.date()))
        
        if company_data.estado_empresa is not None:
            update_fields.append("estado_empresa = @estado_empresa")
            query_params.append(bigquery.ScalarQueryParameter("estado_empresa", "STRING", company_data.estado_empresa))
        
        if company_data.motivo_cierre is not None:
            update_fields.append("motivo_cierre = @motivo_cierre")
            query_params.append(bigquery.ScalarQueryParameter("motivo_cierre", "STRING", company_data.motivo_cierre))

        # Always update fecha_actualizacion
        update_fields.append("fecha_actualizacion = @fecha_actualizacion")

        if not update_fields:
            return existing_company

        query = f"""
        UPDATE `{self.table_id}`
        SET {', '.join(update_fields)}
        WHERE empresa_id = @empresa_id
        """

        try:
            job_config = bigquery.QueryJobConfig(query_parameters=query_params)
            query_job = self.client.query(query, job_config=job_config)
            query_job.result()

            # Retrieve the updated company
            updated_company = await self.get_company_by_id(empresa_id)
            return updated_company

        except Exception as e:
            raise DatabaseConnectionError(details={"Company service error": str(e)})

    async def delete_company(self, empresa_id: str) -> bool:
        """Eliminar una empresa"""
        # First check if company exists
        existing_company = await self.get_company_by_id(empresa_id)
        if not existing_company:
            return False

        query = f"""
        DELETE FROM `{self.table_id}`
        WHERE empresa_id = @empresa_id
        """

        query_params = [
            bigquery.ScalarQueryParameter("empresa_id", "STRING", empresa_id)
        ]

        try:
            job_config = bigquery.QueryJobConfig(query_parameters=query_params)
            query_job = self.client.query(query, job_config=job_config)
            query_job.result()
            return True

        except Exception as e:
            raise DatabaseConnectionError(details={"Company service error": str(e)})


company_service = CompanyService()
