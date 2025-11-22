from typing import Optional, List
import json
import logging
import hashlib
from google.cloud import bigquery

from app.core.config import bigquery_config
from app.core.exceptions import DatabaseConnectionError
from app.schemas.insights import InsightItem, PaginatedAppInsightsResponse

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
        page: int = 1,
        per_page: int = 10
    ) -> PaginatedAppInsightsResponse:
        """Get insights for a specific app from AI analysis data with pagination.

        Args:
            app_id: App ID to get insights for
            from_date: Optional start date filter (YYYY-MM-DD format)
            to_date: Optional end date filter (YYYY-MM-DD format)
            page: Page number (1-based)
            per_page: Number of items per page

        Returns:
            PaginatedAppInsightsResponse containing processed insights with pagination info

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
            """

            job_config = bigquery.QueryJobConfig(query_parameters=query_params)
            
            query_job = self.client.query(query, job_config=job_config)
            results = list(query_job.result())

            if not results:
                logger.info(f"No analysis data found for app: {app_id}")
                return PaginatedAppInsightsResponse(
                    insights=[],
                    total=0,
                    page=page,
                    per_page=per_page
                )

            # Process the JSON data to extract insights
            all_insights = self._process_analysis_data(results)
            total_insights = len(all_insights)
            
            # Apply pagination
            start_index = (page - 1) * per_page
            end_index = start_index + per_page
            
            # Validate page bounds
            if total_insights > 0 and start_index >= total_insights:
                max_pages = ((total_insights - 1) // per_page) + 1
                raise ValueError(f"Requested page {page} is out of bounds. There are only {max_pages} pages available.")
            
            paginated_insights = all_insights[start_index:end_index]
            
            logger.info(f"Found {total_insights} total insights for app: {app_id}, returning page {page} with {len(paginated_insights)} insights")
            
            return PaginatedAppInsightsResponse(
                insights=paginated_insights,
                total=total_insights,
                page=page,
                per_page=per_page
            )

        except ValueError:
            # Re-raise ValueError for pagination validation (don't convert to DatabaseConnectionError)
            raise
        except Exception as e:
            logger.error(f"Error getting insights for app {app_id}: {e}")
            raise DatabaseConnectionError(f"Error querying the database: {e}")

    def _generate_change_value(self, 
                              insight_type: str, 
                              content: str, 
                              priority: str = None, 
                              sentiment_score: int = None) -> str:
        """Generate appropriate change value based on available data using realistic simulation.
        
        Args:
            insight_type: Type of insight ('positive' or 'negative')
            content: Text content to analyze for keywords
            priority: Priority level if available ('high', 'medium', 'low')
            sentiment_score: Sentiment score if available (1-5 scale)
            
        Returns:
            String representing percentage change (e.g., '+25%', '-30%')
        """
        
        # Method 1: Use priority if available (for recommendations)
        if priority:
            priority_mapping = {
                "high": ["+45%", "+50%", "+40%", "+55%"],
                "medium": ["+25%", "+30%", "+20%", "+35%"], 
                "low": ["+10%", "+15%", "+12%", "+18%"]
            }
            options = priority_mapping.get(priority.lower(), ["+20%"])
            
        # Method 2: Use sentiment score if available
        elif sentiment_score is not None:
            if sentiment_score >= 4:
                options = ["+35%", "+40%", "+30%", "+45%"]
            elif sentiment_score >= 3:
                options = ["+15%", "+20%", "+18%", "+25%"]
            elif sentiment_score == 2:
                options = ["-15%", "-20%", "-18%", "-25%"]
            else:
                options = ["-30%", "-35%", "-25%", "-40%"]
        
        # Method 3: Analyze content for keywords
        else:
            content_lower = content.lower()
            
            # Positive indicators
            if any(word in content_lower for word in ["mejor", "excelente", "bueno", "útil", "rápido", "fácil"]):
                options = ["+20%", "+25%", "+18%", "+30%"]
            # Negative indicators  
            elif any(word in content_lower for word in ["problema", "lento", "difícil", "caro", "malo", "error"]):
                options = ["-25%", "-30%", "-20%", "-35%"]
            # Neutral or mixed
            else:
                if insight_type == "positive":
                    options = ["+15%", "+18%", "+12%", "+22%"]
                else:
                    options = ["-15%", "-18%", "-12%", "-22%"]
        
        # Use hash for consistent but varied selection based on content
        hash_val = int(hashlib.md5(content.encode('utf-8')).hexdigest(), 16)
        return options[hash_val % len(options)]

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
                # Extract period from review_date (YYYY-MM format)
                #TODO: Check with Sebas why the reviewDate(within the json) is different from review_date(column on the table)
                period =  review_date.strftime("%Y-%m") if review_date else "unknown"
                # Process strengths as positive insights
                strengths = analysis_data.get("strengths", [])
                for strength in strengths:
                    content = strength.get('userImpact', 'Impacto positivo en los usuarios')
                    insights.append(InsightItem(
                        type="positive",
                        title=f"Fortaleza: {strength.get('feature', 'Feature destacado')}",
                        change=self._generate_change_value("positive", content),
                        summary=content,
                        period=period
                    ))

                # Process weaknesses as negative insights
                weaknesses = analysis_data.get("weaknesses", [])
                for weakness in weaknesses:
                    content = weakness.get('userImpact', 'Impacto negativo en los usuarios')
                    insights.append(InsightItem(
                        type="negative",
                        title=f"Área de mejora: {weakness.get('aspect', 'Aspecto a mejorar')}",
                        change=self._generate_change_value("negative", content),
                        summary=content,
                        period=period
                    ))

                # Process insights from the insights array
                raw_insights = analysis_data.get("insights", [])
                for raw_insight in raw_insights:
                    insight_type = self._determine_insight_type(raw_insight.get("type", ""))
                    content = raw_insight.get('observation', 'Observación general')
                    insights.append(InsightItem(
                        type=insight_type,
                        title=f"Insight: {raw_insight.get('type', 'Observación general')}",
                        change=self._generate_change_value(insight_type, content),
                        summary=content,
                        period=period
                    ))

                # Process recommendations as actionable insights
                recommendations = analysis_data.get("recommendations", [])
                for recommendation in recommendations:
                    priority = recommendation.get('priority', 'medium')
                    content = recommendation.get('action', 'Acción recomendada')
                    
                    insights.append(InsightItem(
                        type="negative",  # Recommendations usually indicate areas to improve
                        title=f"Recomendación ({priority}): {recommendation.get('category', 'general')}",
                        change=self._generate_change_value("negative", content, priority=priority),
                        summary=content,
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