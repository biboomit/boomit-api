from typing import Tuple, List, Optional
from datetime import datetime, timedelta
from google.cloud import bigquery
import logging
import json
import httpx
import os
import pandas as pd
import random
import string

from app.core.config import bigquery_config
from app.core.exceptions import DatabaseConnectionError
from app.integrations.openai.emerging_themes_batch import (
    OpenAIEmergingThemesBatchIntegration,
)
from app.integrations.openai.emerging_themes_prompt import EMERGING_THEMES_PROMPT

logger = logging.getLogger(__name__)


class EmergingThemesService:
    """Service for analyzing emerging themes from app reviews using AI."""

    def __init__(self):
        self.client = bigquery_config.get_client()
        self.reviews_table = bigquery_config.get_table_id("DIM_REVIEWS_HISTORICO")
        self.maestro_table = bigquery_config.get_table_id("DIM_MAESTRO_REVIEWS")
        self.emerging_themes_table = bigquery_config.get_table_id_with_dataset(
            "AIOutput", "EMERGING_THEMES"
        )
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

    async def analyze_emerging_themes_global(
        self, app_id: str, force_new_analysis: bool = False
    ) -> dict:
        """
        Analiza temas emergentes de manera global usando un solo prompt y request síncrona a OpenAI.
        """
        try:
            # Calcular rango de fechas (últimos 90 días)
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
                        f"Age: {cached_analysis['cache_age_hours']:.1f} hours"
                    )
                    
                    # Return cached batch info with updated metadata
                    cached_analysis["from_cache"] = True

                    return cached_analysis  # None for batch since it's cached

            # Get app metadata (name and category)
            app_metadata = await self._get_app_metadata(app_id)

            if not app_metadata:
                raise ValueError(f"App with ID '{app_id}' not found")

            # Fetch reviews from last 90 days
            reviews = await self._get_reviews_last_90_days(app_id, start_date, end_date)

            if not reviews:
                raise ValueError(f"No reviews found for app '{app_id}' in the last 90 days")
            if len(reviews) < 20:
                raise ValueError( f"Not enough reviews ({len(reviews)}) for app '{app_id}' to perform analysis. Minimum 20 required.")

            logger.info(
                f"Found {len(reviews)} reviews for app {app_id} "
                f"from {start_date.date()} to {end_date.date()}"
            )

            # Build global prompt
            system_prompt = EMERGING_THEMES_PROMPT.format(
                app_id=app_id,
                app_name=app_metadata["app_name"],
                app_category=app_metadata["app_category"],
                total_reviews=len(reviews),
                start_date=start_date.strftime("%Y-%m-%d"),
                end_date=end_date.strftime("%Y-%m-%d"),
            )
            # Build user content
            formatted_reviews = []

            for idx, (content, score, review_date) in enumerate(reviews, 1):
                date_str = review_date.strftime("%Y-%m-%d")
                formatted_review = f"Review {idx} | {date_str} | Score: {score}/5\n{content}\n"
                formatted_reviews.append(formatted_review)

            # Join all reviews with separator
            all_reviews = "\n" + "="*80 + "\n\n".join(formatted_reviews)
            user_content = f"""A continuación se presentan {len(reviews)} reviews de usuarios para analizar: \n\n{all_reviews}\n\nAnaliza estas reviews e identifica los temas emergentes según las instrucciones proporcionadas en el prompt del sistema."""

            # Prepare request to OpenAI
            api_key = os.getenv("OPENAI_API_KEY")
            model = os.getenv("OPENAI_MODEL", "gpt-4o")
            url = "https://api.openai.com/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            body = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content}
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0.7,
                "max_tokens": 4000
            }

            # OpenAI request
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(url, headers=headers, json=body)
                resp.raise_for_status()
                data = resp.json()

            # Extract emerging themes from response
            if (
                isinstance(data, dict)
                and "choices" in data
                and isinstance(data["choices"], list)
                and len(data["choices"]) > 0
                and "message" in data["choices"][0]
                and "content" in data["choices"][0]["message"]
            ):
                content = data["choices"][0]["message"]["content"]
                try:
                    themes_json = json.loads(content)
                except Exception:
                    themes_json = {"themes": []}
            else:
                themes_json = {"themes": []}

            # Save in BigQuery (EMERGING_THEMES)
            analyzed_at = datetime.utcnow()
            created_at = analyzed_at

            def generar_codigo():
                numbers = "".join(random.choices(string.digits, k=6))
                return f"et{numbers}"
            
            analysis_id = generar_codigo()
            cache_key = f"{app_id}_{start_date.date()}_{end_date.date()}"
            df = pd.DataFrame([{
                "analysis_id": analysis_id,
                "app_id": app_id,
                "batch_id": None,
                "json_data": json.dumps(themes_json, ensure_ascii=False),
                "analysis_period_start": start_date.date(),
                "analysis_period_end": end_date.date(),
                "total_reviews_analyzed": len(reviews),
                "analyzed_at": analyzed_at,
                "created_at": created_at,
                "cache_key": cache_key
            }])
            bq_client = self.client
            table_id = self.emerging_themes_table
            job_config = bigquery.LoadJobConfig(write_disposition="WRITE_APPEND")
            job = bq_client.load_table_from_dataframe(df, table_id, job_config=job_config)
            job.result()

            # Build response dict
            result = {
                "app_id": app_id,
                "app_name": app_metadata["app_name"],
                "app_category": app_metadata["app_category"],
                "total_reviews_analyzed": len(reviews),
                "analysis_period_start": start_date.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "analysis_period_end": end_date.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "themes": f"Go to /emerging-themes/{app_id}/latest to fetch the themes",
                "analyzed_at": analyzed_at.strftime("%Y-%m-%dT%H:%M:%SZ")
            }
            return result
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
                bigquery.ScalarQueryParameter("start_date", "DATE", start_date.date()),
                bigquery.ScalarQueryParameter("end_date", "DATE", end_date.date()),
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
                    parsed_data = json.loads(row.json_data)
                    # Handle case where data might be wrapped in {"themes": [...]}
                    if isinstance(parsed_data, dict) and "themes" in parsed_data:
                        themes = parsed_data["themes"]
                    elif isinstance(parsed_data, list):
                        themes = parsed_data
                    else:
                        logger.warning(f"Unexpected JSON structure: {type(parsed_data)}")
                        themes = []
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse themes JSON: {e}")
                    themes = []

            # Get app metadata (name and category) from maestro table
            app_metadata = await self._get_app_metadata(app_id)
            
            return {
                "app_id": row.app_id,
                "batch_id": row.batch_id,
                "app_name": app_metadata["app_name"] if app_metadata else "Unknown App",
                "app_category": app_metadata["app_category"] if app_metadata else "Unknown Category",
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
            total_reviews_analyzed,
            analysis_period_start,
            analysis_period_end,
            created_at,
            TIMESTAMP_DIFF(CURRENT_TIMESTAMP(), created_at, HOUR) as age_hours
        FROM `{self.emerging_themes_table}`
        WHERE cache_key = @cache_key
            AND TIMESTAMP_DIFF(CURRENT_TIMESTAMP(), created_at, HOUR) <= @expiration_hours
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
            logger.debug(f"Cache key used: {cache_key}")
            logger.debug(f"Cache query results: {results}")

            if not results:
                return None

            row = results[0]
            return {
                "batch_id": row.batch_id,
                "app_id": row.app_id,
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