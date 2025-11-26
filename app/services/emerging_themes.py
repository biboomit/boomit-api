from typing import Tuple, List
from datetime import datetime, timedelta
from google.cloud import bigquery
import logging

from app.core.config import bigquery_config
from app.core.exceptions import DatabaseConnectionError
from app.integrations.openai.emerging_themes_batch import (
    OpenAIEmergingThemesBatchIntegration,
)

logger = logging.getLogger(__name__)


class EmergingThemesService:
    """Service for analyzing emerging themes from app reviews using AI."""

    def __init__(self):
        self.client = bigquery_config.get_client()
        self.reviews_table = bigquery_config.get_table_id("DIM_REVIEWS_HISTORICO")
        self.maestro_table = bigquery_config.get_table_id("DIM_MAESTRO_REVIEWS")
        self.batch_integration = OpenAIEmergingThemesBatchIntegration()

    async def analyze_emerging_themes(self, app_id: str) -> Tuple[any, dict]:
        """
        Analyze emerging themes for an app based on reviews from the last 90 days.

        Args:
            app_id: Application ID to analyze

        Returns:
            Tuple containing (batch object, metadata dict)
        
        Raises:
            DatabaseConnectionError: If BigQuery query fails
            ValueError: If app not found or has no reviews
        """
        try:
            # Get app metadata (name and category)
            app_metadata = await self._get_app_metadata(app_id)
            
            if not app_metadata:
                raise ValueError(f"App with ID '{app_id}' not found")

            # Calculate date range (last 90 days)
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=90)

            # Fetch reviews from last 90 days
            reviews = await self._get_reviews_last_90_days(app_id, start_date, end_date)

            if not reviews:
                raise ValueError(
                    f"No reviews found for app '{app_id}' in the last 90 days"
                )

            logger.info(
                f"Found {len(reviews)} reviews for app {app_id} "
                f"from {start_date.date()} to {end_date.date()}"
            )

            # Send to OpenAI Batch API
            uploaded_file, batch = self.batch_integration.analyze_emerging_themes(
                app_id=app_id,
                app_name=app_metadata["app_name"],
                app_category=app_metadata["app_category"],
                reviews=reviews,
                start_date=start_date,
                end_date=end_date,
            )

            # Prepare metadata for response
            metadata = {
                "app_id": app_id,
                "app_name": app_metadata["app_name"],
                "app_category": app_metadata["app_category"],
                "total_reviews": len(reviews),
                "start_date": start_date,
                "end_date": end_date,
                "batch_id": batch.id,
                "uploaded_file_id": uploaded_file.id,
            }

            logger.info(f"Batch created successfully: {batch.id}")

            return batch, metadata

        except ValueError as e:
            logger.error(f"Validation error: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error analyzing emerging themes: {str(e)}")
            raise DatabaseConnectionError(
                f"Failed to analyze emerging themes for app {app_id}: {str(e)}"
            )

    async def _get_app_metadata(self, app_id: str) -> dict:
        """
        Get app name and category from DIM_MAESTRO_REVIEWS table.

        Args:
            app_id: Application ID

        Returns:
            Dict with app_name and app_category, or None if not found
        """
        query = f"""
        SELECT 
            app_name,
            app_categoria as app_category
        FROM `{self.maestro_table}`
        WHERE app_id = @app_id
        LIMIT 1
        """

        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("app_id", "STRING", app_id)
            ]
        )

        try:
            query_job = self.client.query(query, job_config=job_config)
            results = list(query_job.result())

            if not results:
                return None

            row = results[0]
            return {
                "app_name": row.app_name or "Unknown App",
                "app_category": row.app_category or "Unknown Category",
            }

        except Exception as e:
            logger.error(f"Error fetching app metadata: {str(e)}")
            raise DatabaseConnectionError(f"Failed to fetch app metadata: {str(e)}")

    async def _get_reviews_last_90_days(
        self, app_id: str, start_date: datetime, end_date: datetime
    ) -> List[Tuple[str, int, datetime]]:
        """
        Fetch reviews for an app from the last 90 days.

        Args:
            app_id: Application ID
            start_date: Start date for filtering
            end_date: End date for filtering

        Returns:
            List of tuples: (content, score, fecha)
        """
        query = f"""
        SELECT 
            content,
            score,
            fecha
        FROM `{self.reviews_table}`
        WHERE app_id = @app_id
            AND fecha >= @start_date
            AND fecha <= @end_date
            AND content IS NOT NULL
            AND TRIM(content) != ''
        ORDER BY fecha DESC
        LIMIT 1500
        """

        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("app_id", "STRING", app_id),
                bigquery.ScalarQueryParameter("start_date", "TIMESTAMP", start_date),
                bigquery.ScalarQueryParameter("end_date", "TIMESTAMP", end_date),
            ]
        )

        try:
            query_job = self.client.query(query, job_config=job_config)
            results = query_job.result()

            reviews = []
            for row in results:
                reviews.append((row.content, row.score, row.fecha))

            return reviews

        except Exception as e:
            logger.error(f"Error fetching reviews: {str(e)}")
            raise DatabaseConnectionError(f"Failed to fetch reviews: {str(e)}")


# Singleton instance
emerging_themes_service = EmergingThemesService()
