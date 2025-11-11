from typing import Optional, List
import json
import logging
from datetime import datetime
from google.cloud import bigquery

from app.core.config import bigquery_config
from app.core.exceptions import DatabaseConnectionError
from app.schemas.insights import InsightItem, AppInsightsResponse

logger = logging.getLogger(__name__)


class InsightsService:
    """Service for retrieving and processing app insights from AI analysis data"""

    def __init__(self) -> None:
        self.client = bigquery_config.get_client()
        self.analysis_table_id = bigquery_config.get_table_id_with_dataset(
            "AIOutput", "Reviews_Analysis"
        )

    async def get_app_insights(
        self,
        app_id: str,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        country: Optional[str] = None
    ) -> AppInsightsResponse:
        """Get insights for a specific app from AI analysis data.

        Args:
            app_id: App ID to get insights for
            from_date: Optional start date filter (YYYY-MM-DD format)
            to_date: Optional end date filter (YYYY-MM-DD format)
            country: Optional country filter

        Returns:
            AppInsightsResponse containing processed insights

        Raises:
            DatabaseConnectionError: If query fails
        """
        try:
            logger.info(f"Getting insights for app: {app_id}")
            
            # Build WHERE conditions
            where_conditions = ["app_id = @app_id", "json_data IS NOT NULL"]
            query_params = [
                bigquery.ScalarQueryParameter("app_id", "STRING", app_id)
            ]

            # Add date filters if provided
            if from_date:
                where_conditions.append("review_date >= @from_date")
                query_params.append(
                    bigquery.ScalarQueryParameter("from_date", "DATE", from_date)
                )

            if to_date:
                where_conditions.append("review_date <= @to_date")
                query_params.append(
                    bigquery.ScalarQueryParameter("to_date", "DATE", to_date)
                )

            where_clause = "WHERE " + " AND ".join(where_conditions)

            # Query for AI analysis data
            query = f"""
            SELECT 
                json_data,
                review_date,
                analyzed_at
            FROM `{self.analysis_table_id}`
            {where_clause}
            ORDER BY analyzed_at DESC
            LIMIT 1
            """

            job_config = bigquery.QueryJobConfig(query_parameters=query_params)
            
            query_job = self.client.query(query, job_config=job_config)
            results = list(query_job.result())

            if not results:
                logger.info(f"No analysis data found for app: {app_id}")
                return AppInsightsResponse(insights=[])

            # Process the JSON data to extract insights
            insights = self._process_analysis_data(results)
            
            logger.info(f"Found {len(insights)} insights for app: {app_id}")
            return AppInsightsResponse(insights=insights)

        except Exception as e:
            logger.error(f"Error getting insights for app {app_id}: {e}")
            raise DatabaseConnectionError(f"Error querying the database: {e}")

    def _process_analysis_data(self, results: List) -> List[InsightItem]:
        """Process raw analysis data to extract structured insights.

        Args:
            results: Raw query results from BigQuery

        Returns:
            List of InsightItem objects
        """
        insights = []
        
        for row in results:
            try:
                # Parse the JSON data
                analysis_data = json.loads(row.json_data)
                review_date = row.review_date
                
                # Extract period from date (YYYY-MM format)
                period = review_date.strftime("%Y-%m") if review_date else "unknown"
                
                # Process strengths as positive insights
                strengths = analysis_data.get("strengths", [])
                for strength in strengths:
                    insights.append(InsightItem(
                        type="positive",
                        title=f"Fortaleza: {strength.get('feature', 'Feature destacado')}",
                        change="+",  # Default positive indicator
                        summary=strength.get('userImpact', 'Impacto positivo en los usuarios'),
                        period=period
                    ))

                # Process weaknesses as negative insights
                weaknesses = analysis_data.get("weaknesses", [])
                for weakness in weaknesses:
                    insights.append(InsightItem(
                        type="negative",
                        title=f"Área de mejora: {weakness.get('aspect', 'Aspecto a mejorar')}",
                        change="-",  # Default negative indicator
                        summary=weakness.get('userImpact', 'Impacto negativo en los usuarios'),
                        period=period
                    ))

                # Process insights from the insights array
                raw_insights = analysis_data.get("insights", [])
                for raw_insight in raw_insights:
                    insight_type = self._determine_insight_type(raw_insight.get("type", ""))
                    insights.append(InsightItem(
                        type=insight_type,
                        title=f"Insight: {raw_insight.get('type', 'Observación general')}",
                        change="~",  # Default neutral indicator for insights
                        summary=raw_insight.get('observation', 'Observación general'),
                        period=period
                    ))

                # Process recommendations as actionable insights
                recommendations = analysis_data.get("recommendations", [])
                for recommendation in recommendations:
                    priority = recommendation.get('priority', 'medium')
                    change_indicator = self._get_priority_indicator(priority)
                    
                    insights.append(InsightItem(
                        type="negative",  # Recommendations usually indicate areas to improve
                        title=f"Recomendación ({priority}): {recommendation.get('category', 'general')}",
                        change=change_indicator,
                        summary=recommendation.get('action', 'Acción recomendada'),
                        period=period
                    ))

            except (json.JSONDecodeError, KeyError, AttributeError) as e:
                logger.warning(f"Error processing analysis data: {e}")
                continue

        # Remove duplicates and sort by relevance
        return self._deduplicate_and_sort_insights(insights)

    def _determine_insight_type(self, insight_type: str) -> str:
        """Determine if an insight should be categorized as positive or negative."""
        negative_types = [
            "feature_gap", "adoption_barrier", "satisfaction_driver", 
            "technical_issue", "usability_issue"
        ]
        
        if insight_type.lower() in negative_types:
            return "negative"
        else:
            return "positive"

    def _get_priority_indicator(self, priority: str) -> str:
        """Get change indicator based on priority level."""
        priority_indicators = {
            "high": "---",
            "medium": "--", 
            "low": "-"
        }
        return priority_indicators.get(priority.lower(), "-")

    def _deduplicate_and_sort_insights(self, insights: List[InsightItem]) -> List[InsightItem]:
        """Remove duplicate insights and sort by relevance."""
        # Simple deduplication based on title similarity
        seen_titles = set()
        unique_insights = []
        
        for insight in insights:
            # Create a normalized title for comparison
            normalized_title = insight.title.lower().strip()
            
            if normalized_title not in seen_titles:
                seen_titles.add(normalized_title)
                unique_insights.append(insight)

        # Sort: negative insights first (more actionable), then by period descending
        unique_insights.sort(
            key=lambda x: (
                0 if x.type == "negative" else 1,  # Negative first
                x.period  # Then by period
            ),
            reverse=True
        )

        return unique_insights


# Singleton instance
insights_service = InsightsService()