from typing import Optional
from google.cloud import bigquery
from app.core.exceptions import DatabaseConnectionError
from app.schemas.apps import AppDetailsResponse
from app.core.config import bigquery_config
from datetime import datetime, date
import logging

logger = logging.getLogger(__name__)


class AppService:
    def __init__(self) -> None:
        self.client = bigquery_config.get_client()
        self.maestro_table = bigquery_config.get_table_id("DIM_MAESTRO_REVIEWS")
        self.historico_table = bigquery_config.get_table_id("DIM_REVIEWS_HISTORICO")

    async def get_app_details(self, app_id: str) -> Optional[AppDetailsResponse]:
        """Get app details by app_id using DIM_MAESTRO_REVIEWS and DIM_REVIEWS_HISTORICO.

        Args:
            app_id: App ID to fetch details for

        Returns:
            AppDetailsResponse if found, None otherwise

        Raises:
            DatabaseConnectionError: If query fails
        """
        
        # Query para obtener datos principales de DIM_MAESTRO_REVIEWS
        main_query = f"""
        SELECT DISTINCT
            app_id,
            app_name,
            LOWER(SO) as store,
            app_desarrollador as developer,
            app_descargas as downloads,
            app_icon_url as icon_url,
            app_categoria as category,
            fecha_actualizacion as last_update
        FROM `{self.maestro_table}`
        WHERE app_id = @app_id
        LIMIT 1
        """

        # Query para obtener ratings de DIM_REVIEWS_HISTORICO
        ratings_query = f"""
        SELECT
            AVG(score) as average_rating,
            COUNT(*) as total_ratings
        FROM `{self.historico_table}`
        WHERE app_id = @app_id
        """

        query_params = [
            bigquery.ScalarQueryParameter("app_id", "STRING", app_id)
        ]

        job_config = bigquery.QueryJobConfig(query_parameters=query_params)

        try:
            logger.info(f"Fetching app details for app_id: {app_id}")

            # Ejecutar query principal
            main_job = self.client.query(main_query, job_config=job_config)
            main_results = list(main_job.result())

            if not main_results:
                logger.warning(f"App not found: {app_id}")
                return None

            main_data = main_results[0]

            # Ejecutar query de ratings
            ratings_job = self.client.query(ratings_query, job_config=job_config)
            ratings_results = list(ratings_job.result())

            # Procesar datos de ratings
            rating_average = None
            total_ratings = None
            
            if ratings_results and ratings_results[0].total_ratings > 0:
                rating_data = ratings_results[0]
                rating_average = round(rating_data.average_rating, 2) if rating_data.average_rating else None
                total_ratings = rating_data.total_ratings

            # Procesar fecha de actualización
            last_update = main_data.last_update
            if isinstance(last_update, datetime):
                last_update = last_update.date()
            elif last_update is None:
                last_update = date.today()

            # Manejar valores nulos con defaults seguros
            developer = main_data.developer if main_data.developer else "Unknown Developer"
            downloads = main_data.downloads if main_data.downloads is not None else 0
            icon_url = main_data.icon_url if main_data.icon_url else ""
            category = main_data.category if main_data.category else "Unknown"

            # Crear respuesta
            app_details = AppDetailsResponse(
                app_id=main_data.app_id,
                app_name=main_data.app_name,
                store=main_data.store,
                developer=developer,
                rating_average=rating_average,
                total_ratings=total_ratings,
                downloads=downloads,
                last_update=last_update,
                icon_url=icon_url,
                category=category
            )

            logger.info(f"App details retrieved successfully: {app_id}")
            return app_details

        except Exception as e:
            logger.error(f"Error fetching app details for {app_id}: {e}")
            raise DatabaseConnectionError(f"Error querying the database: {e}")


# Singleton instance
app_service = AppService()