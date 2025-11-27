from typing import Tuple, List, Optional
from datetime import datetime, timedelta
from google.cloud import bigquery
import logging
import json

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
        self.emerging_themes_table = bigquery_config.get_table_id("EMERGING_THEMES")
        self.batch_integration = OpenAIEmergingThemesBatchIntegration()
        self.cache_expiration_hours = 24  # Caché válido por 24 horas

    async def analyze_emerging_themes(
        self, app_id: str, force_new_analysis: bool = False
    ) -> Tuple[any, dict]:
        """
        Analyze emerging themes for an app based on reviews from the last 90 days.
        
        Implements caching to avoid duplicate analysis:
        - If analysis exists within last 24h and force_new_analysis=False, returns cached result
        - Otherwise creates new analysis

        Args:
            app_id: Application ID to analyze
            force_new_analysis: If True, bypass cache and create new analysis

        Returns:
            Tuple containing (batch object, metadata dict)
        
        Raises:
            DatabaseConnectionError: If BigQuery query fails
            ValueError: If app not found or has no reviews
        """
        try:
            # Calculate date range (last 90 days)
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=90)
            
            # Generate cache key
            cache_key = self._generate_cache_key(app_id, start_date, end_date)
            
            # Check for cached analysis (unless forced)
            if not force_new_analysis:
                cached_analysis = await self._find_cached_analysis(cache_key)
                
                if cached_analysis:
                    logger.info(
                        f"Returning cached analysis for {app_id}. "
                        f"Batch ID: {cached_analysis['batch_id']}, "
                        f"Age: {cached_analysis['cache_age_hours']:.1f} hours"
                    )
                    
                    # Return cached batch info with updated metadata
                    cached_analysis["from_cache"] = True
                    return None, cached_analysis  # None for batch since it's cached
            
            # Get app metadata (name and category)
            app_metadata = await self._get_app_metadata(app_id)
            
            if not app_metadata:
                raise ValueError(f"App with ID '{app_id}' not found")

            # Fetch reviews from last 90 days
            reviews = await self._get_reviews_last_90_days(app_id, start_date, end_date)

            if not reviews:
                raise ValueError(
                    f"No reviews found for app '{app_id}' in the last 90 days"
                )
            
            if len(reviews) < 20:
                raise ValueError(
                    f"Not enough reviews ({len(reviews)}) for app '{app_id}' to perform analysis. Minimum 20 required."
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
                "cache_key": cache_key,
                "from_cache": False,
                "cache_age_hours": 0.0,
            }

            logger.info(f"New batch created successfully: {batch.id}")

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

    async def get_latest_completed_analysis(self, app_id: str) -> Optional[dict]:
        """
        Retrieve the latest completed emerging themes analysis for an app.

        Args:
            app_id: Application ID

        Returns:
            Dict with analysis results including themes, or None if not found
        """
        query = f"""
        SELECT 
            analysis_id,
            app_id,
            batch_id,
            app_name,
            app_category,
            json_data,
            analysis_period_start,
            analysis_period_end,
            total_reviews_analyzed,
            analyzed_at,
            created_at
        FROM `{self.emerging_themes_table}`
        WHERE app_id = @app_id
        ORDER BY created_at DESC
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
            
            # Parse themes from JSON string
            themes = []
            if row.json_data:
                try:
                    themes = json.loads(row.json_data)
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse themes JSON: {e}")
                    themes = []

            return {
                "app_id": row.app_id,
                "batch_id": row.batch_id,
                "app_name": row.app_name,
                "app_category": row.app_category,
                "total_reviews_analyzed": row.total_reviews_analyzed,
                "analysis_period_start": row.analysis_period_start,
                "analysis_period_end": row.analysis_period_end,
                "themes": themes,
                "analyzed_at": row.analyzed_at,
            }

        except Exception as e:
            logger.error(f"Error retrieving latest analysis: {str(e)}")
            raise DatabaseConnectionError(f"Failed to retrieve analysis: {str(e)}")

    def _generate_cache_key(
        self, app_id: str, start_date: datetime, end_date: datetime
    ) -> str:
        """
        Generate a unique cache key for an analysis period.

        Args:
            app_id: Application ID
            start_date: Start date of analysis
            end_date: End date of analysis

        Returns:
            Cache key string (format: app_id_YYYY-MM-DD_YYYY-MM-DD)
        """
        return f"{app_id}_{start_date.date()}_{end_date.date()}"

    async def _find_cached_analysis(self, cache_key: str) -> dict:
        """
        Look for existing analysis within cache expiration window.

        Args:
            cache_key: Cache key to search for

        Returns:
            Dict with cached analysis metadata, or None if not found/expired
        """
        query = f"""
        SELECT 
            batch_id,
            app_id,
            app_name,
            app_category,
            total_reviews_analyzed,
            analysis_period_start,
            analysis_period_end,
            created_at,
            TIMESTAMP_DIFF(CURRENT_TIMESTAMP(), created_at, HOUR) as age_hours
        FROM `{self.emerging_themes_table}`
        WHERE cache_key = @cache_key
            AND age_hours <= @expiration_hours
        ORDER BY created_at DESC
        LIMIT 1
        """

        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("cache_key", "STRING", cache_key),
                bigquery.ScalarQueryParameter(
                    "expiration_hours", "INT64", self.cache_expiration_hours
                ),
            ]
        )

        try:
            query_job = self.client.query(query, job_config=job_config)
            results = list(query_job.result())

            if not results:
                return None

            row = results[0]
            return {
                "batch_id": row.batch_id,
                "app_id": row.app_id,
                "app_name": row.app_name,
                "app_category": row.app_category,
                "total_reviews": row.total_reviews_analyzed,
                "start_date": row.analysis_period_start,
                "end_date": row.analysis_period_end,
                "created_at": row.created_at,
                "cache_age_hours": float(row.age_hours) if row.age_hours else 0.0,
            }

        except Exception as e:
            logger.warning(f"Error checking cache (continuing with new analysis): {str(e)}")
            return None


# Singleton instance
emerging_themes_service = EmergingThemesService()
