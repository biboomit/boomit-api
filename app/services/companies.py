from typing import List, Optional
from schemas.companies import CompanyResponse, CompanyInternal
from datetime import datetime
from app.core.config import bigquery_config

class CompanyService:
    def __init__(self):
        self.client = bigquery_config.get_client()
        self.table_id = bigquery_config.get_table_id("DIM_EMPRESA")


    async def get_companies(self, skip: int = 0, limit: int = 10) -> tuple[List[CompanyInternal], int]:
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
        
        raise NotImplementedError("TODO: TERMINAR ESTA FUNCION")
    
company_service = CompanyService()