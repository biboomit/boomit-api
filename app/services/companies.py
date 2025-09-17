from typing import List, Optional
from app.core.exceptions import DatabaseConnectionError
from app.schemas.companies import CompanyResponse, CompanyInternal
from datetime import datetime
from app.core.config import bigquery_config



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
        LIMIT {limit}
        OFFSET {skip}
        """

        checkpoint = 0
        try:
            query_job = self.client.query(query)
            results = query_job.result()
            companies = [CompanyInternal(**dict(row)) for row in results]
            
            checkpoint = 1

            count_query = f"SELECT COUNT(*) as total FROM `{self.table_id}`"
            count_job = self.client.query(count_query)
            count_result = count_job.result()
            total_count = list(count_result)[0].total

            return companies, total_count

        except Exception as e:
            print(f"Checkpoint {checkpoint} - Error: {e}")
            raise DatabaseConnectionError(details={"Company service error": str(e)})


company_service = CompanyService()
