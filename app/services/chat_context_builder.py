"""
Chat context builder service.

Loads relevant analysis data from BigQuery to provide context for AI chat responses.
"""

import logging
from typing import Dict, Any, Optional, List
from google.cloud import bigquery
from datetime import datetime, timedelta

from app.core.config import settings
from app.core.exceptions import DatabaseConnectionError

logger = logging.getLogger(__name__)


class ChatContextBuilder:
    """
    Builds context for chat sessions by loading relevant analysis data.
    
    Context includes:
    - Sentiment summary from AI analysis
    - Emerging themes
    - Sample reviews (positive and negative)
    """
    
    def __init__(self):
        """Initialize BigQuery client using config standard."""
        from app.core.config import bigquery_config
        self.client = bigquery_config.get_client()
        self.reviews_table = bigquery_config.get_table_id("DIM_REVIEWS_HISTORICO")
        self.analysis_table = bigquery_config.get_table_id_with_dataset("AIOutput", "Reviews_Analysis")
        self.themes_table = bigquery_config.get_table_id_with_dataset("AIOutput", "EMERGING_THEMES")
        logger.info("ChatContextBuilder initialized")
    
    async def build_context(
        self,
        app_id: str,
        days_back: int = 90
    ) -> Dict[str, Any]:
        """
        Build chat context by loading analysis data for an app.
        
        Args:
            app_id: App identifier
            days_back: Number of days to look back for data (default: 90)
        
        Returns:
            Dictionary with context data:
            {
                "app_id": "com.lulubit",
                "sentiment_summary": {...},
                "emerging_themes": [...],
                "sample_reviews": {"positive": [...], "negative": [...]},
                "stats": {"total_reviews": 100, "avg_rating": 4.2}
            }
        
        Raises:
            DatabaseConnectionError: If query fails
        """
        logger.info(
            f"Building context for app {app_id}, last {days_back} days"
        )
        
        try:
            # Load data in parallel (conceptually - BigQuery executes sequentially)
            sentiment_summary = await self._get_sentiment_summary(app_id, days_back)
            emerging_themes = await self._get_emerging_themes(app_id)
            sample_reviews = await self._get_sample_reviews(app_id, days_back)
            stats = await self._get_app_stats(app_id, days_back)

            context = {
                "app_id": app_id,
                "sentiment_summary": sentiment_summary,
                "emerging_themes": emerging_themes,
                "sample_reviews": sample_reviews,
                "stats": stats,
                "context_generated_at": datetime.utcnow().isoformat()
            }
            
            logger.info(
                f"Context built successfully: {stats.get('total_reviews', 0)} reviews, "
                f"{len(emerging_themes)} themes"
            )
            
            return context
            
        except Exception as e:
            logger.error(f"Error building context: {e}")
            raise DatabaseConnectionError(
                f"Failed to build chat context for app {app_id}",
                details={"app_id": app_id, "error": str(e)}
            )
    
    async def _get_sentiment_summary(
        self,
        app_id: str,
        days_back: int
    ) -> Optional[Dict[str, Any]]:
        """
        Get latest sentiment summary from AI analysis.
        
        Returns aggregated sentiment data from Reviews_Analysis table.
        """
        query = f"""
        WITH latest_analysis AS (
            SELECT
                json_data,
                analyzed_at,
                ROW_NUMBER() OVER (ORDER BY analyzed_at DESC) as rn
            FROM `{self.analysis_table}`
            WHERE app_id = @app_id
              AND review_date >= DATE_SUB(CURRENT_DATE(), INTERVAL @days_back DAY)
              AND JSON_EXTRACT_SCALAR(json_data, '$.sentiment_summary') IS NOT NULL
        )
        SELECT json_data
        FROM latest_analysis
        WHERE rn = 1
        """

        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("app_id", "STRING", app_id),
                bigquery.ScalarQueryParameter("days_back", "INT64", days_back)
            ]
        )
        
        try:
            results = self.client.query(query, job_config=job_config).result()
            row = next(results, None)
            
            if row and row.json_data:
                import json
                data = json.loads(row.json_data)
                return data.get("sentiment_summary")
            
            return None
            
        except Exception as e:
            logger.warning(f"Error fetching sentiment summary: {e}")
            return None
    
    async def _get_emerging_themes(
        self,
        app_id: str
    ) -> List[Dict[str, Any]]:
        """
        Get latest emerging themes from EMERGING_THEMES table.
        
        Returns list of themes with their details.
        """
        query = f"""
        SELECT json_data
        FROM `{self.themes_table}`
        WHERE app_id = @app_id
        ORDER BY analyzed_at DESC
        LIMIT 1
        """

        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("app_id", "STRING", app_id)
            ]
        )
        
        try:
            results = self.client.query(query, job_config=job_config).result()
            row = next(results, None)
            
            if row and row.json_data:
                import json
                data = json.loads(row.json_data)
                return data.get("themes", [])
            
            return []
            
        except Exception as e:
            logger.warning(f"Error fetching emerging themes: {e}")
            return []
    
    async def _get_sample_reviews(
        self,
        app_id: str,
        days_back: int,
        limit: int = 5
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get sample positive and negative reviews.
        
        Returns:
            {
                "positive": [{"text": "...", "rating": 5, "date": "..."}],
                "negative": [{"text": "...", "rating": 1, "date": "..."}]
            }
        """
        # Positive reviews (4-5 stars)
        positive_query = f"""
            SELECT
                review_texto as text,
                review_rating as rating,
                review_fecha as date
            FROM `{self.reviews_table}`
            WHERE app_id = @app_id
                AND review_rating >= 4
                AND review_fecha >= DATE_SUB(CURRENT_DATE(), INTERVAL @days_back DAY)
                AND LENGTH(review_texto) > 50
            ORDER BY review_fecha DESC
            LIMIT @limit
        """

        # Negative reviews (1-2 stars)
        negative_query = f"""
            SELECT
                review_texto as text,
                review_rating as rating,
                review_fecha as date
            FROM `{self.reviews_table}`
            WHERE app_id = @app_id
                AND review_rating <= 2
                AND review_fecha >= DATE_SUB(CURRENT_DATE(), INTERVAL @days_back DAY)
                AND LENGTH(review_texto) > 50
            ORDER BY review_fecha DESC
            LIMIT @limit
        """

        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("app_id", "STRING", app_id),
                bigquery.ScalarQueryParameter("days_back", "INT64", days_back),
                bigquery.ScalarQueryParameter("limit", "INT64", limit)
            ]
        )
        
        try:
            # Get positive reviews
            positive_results = self.client.query(positive_query, job_config=job_config).result()
            positive_reviews = [
                {
                    "text": row.text,
                    "rating": row.rating,
                    "date": row.date.isoformat() if row.date else None
                }
                for row in positive_results
            ]
            
            # Get negative reviews
            negative_results = self.client.query(negative_query, job_config=job_config).result()
            negative_reviews = [
                {
                    "text": row.text,
                    "rating": row.rating,
                    "date": row.date.isoformat() if row.date else None
                }
                for row in negative_results
            ]
            
            return {
                "positive": positive_reviews,
                "negative": negative_reviews
            }
            
        except Exception as e:
            logger.warning(f"Error fetching sample reviews: {e}")
            return {"positive": [], "negative": []}
    
    async def _get_app_stats(
        self,
        app_id: str,
        days_back: int
    ) -> Dict[str, Any]:
        """
        Get basic app statistics.
        
        Returns:
            {
                "total_reviews": 1000,
                "avg_rating": 4.2,
                "period_days": 90
            }
        """
        query = f"""
        SELECT
            COUNT(*) as total_reviews,
            AVG(review_rating) as avg_rating
        FROM `{self.reviews_table}`
        WHERE app_id = @app_id
          AND review_fecha >= DATE_SUB(CURRENT_DATE(), INTERVAL @days_back DAY)
        """

        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("app_id", "STRING", app_id),
                bigquery.ScalarQueryParameter("days_back", "INT64", days_back)
            ]
        )
        
        try:
            results = self.client.query(query, job_config=job_config).result()
            row = next(results, None)
            
            if row:
                return {
                    "total_reviews": int(row.total_reviews) if row.total_reviews else 0,
                    "avg_rating": float(row.avg_rating) if row.avg_rating else 0.0,
                    "period_days": days_back
                }
            
            return {"total_reviews": 0, "avg_rating": 0.0, "period_days": days_back}
            
        except Exception as e:
            logger.warning(f"Error fetching app stats: {e}")
            return {"total_reviews": 0, "avg_rating": 0.0, "period_days": days_back}
    
    # validate_app_ownership removido temporalmente


# Global context builder instance
chat_context_builder = ChatContextBuilder()
