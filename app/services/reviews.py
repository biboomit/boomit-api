import json
from typing import Dict, List, Optional, Tuple, Any
from google.cloud import bigquery
from app.core.exceptions import DatabaseConnectionError
from app.schemas.reviews import (
    ReviewResponse,
    Review,
    ReviewSourceResponse,
    AIAnalysisRequest,
    AnalysisParameters,
)
from app.integrations.openai.batch import OpenAIBatchIntegration
from app.core.config import bigquery_config
from collections import Counter, defaultdict
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class ReviewService:
    def __init__(self) -> None:
        self.client = bigquery_config.get_client()
        self.table_id = bigquery_config.get_table_id("DIM_REVIEWS_HISTORICO")
        self.analysis_table_id = bigquery_config.get_table_id_with_dataset(
            "AIOutput", "Reviews_Analysis"
        )

    async def get_review_sources(
        self,
        skip: int = 0,
        limit: int = 10,
        source: Optional[str] = None,
        has_reviews: Optional[bool] = None,
    ) -> Tuple[List[ReviewSourceResponse], int]:
        """Get list of review sources (apps) with aggregated metadata.

        Args:
            skip: Number of records to skip (for pagination)
            limit: Maximum number of records to return
            source: Filter by source (android/ios) - optional
            has_reviews: Filter apps with/without reviews - optional

        Returns:
            Tuple containing list of ReviewSourceResponse and total count
        """
        where_clause = ""
        having_clause = ""
        query_params = []

        logger.debug(f"Filters received - source: {source}, has_reviews: {has_reviews}")

        if source or has_reviews is not None:
            where_conditions = []
            having_conditions = []

            if source:
                where_conditions.append("LOWER(source) = @source")
                query_params.append(
                    bigquery.ScalarQueryParameter("source", "STRING", source.lower())
                )

            logger.debug(f"Applying has_reviews filter: {has_reviews}")

            if has_reviews is not None:
                if has_reviews:
                    having_conditions.append("COUNT(*) > 0")
                else:
                    having_conditions.append("COUNT(*) = 0")

            logger.debug(f"Where conditions before joining: {where_conditions}")

            if where_conditions:
                where_clause = "WHERE " + " AND ".join(where_conditions)

            if having_conditions:
                having_clause = "HAVING " + " AND ".join(having_conditions)

        data_query = f"""
        SELECT
            app_id,
            LOWER(source) as source,
            COUNT(*) as total_reviews,
            AVG(score) as average_rating,
            MIN(fecha) as first_review_date,
            MAX(fecha) as last_review_date
        FROM `{self.table_id}`
        {where_clause}
        GROUP BY app_id, source
        {having_clause}
        ORDER BY last_review_date DESC
        LIMIT @limit 
        OFFSET @skip
        """

        count_query = f"""
        SELECT COUNT(*) as total
        FROM (
            SELECT app_id, source
            FROM `{self.table_id}`
            {where_clause}
            GROUP BY app_id, source
            {having_clause}
        )
        """

        query_params.append(bigquery.ScalarQueryParameter("limit", "INT64", limit))
        query_params.append(bigquery.ScalarQueryParameter("skip", "INT64", skip))

        job_config = bigquery.QueryJobConfig(query_parameters=query_params)

        try:
            logger.info(
                f"Fetching review sources with filters - source: {source}, has_reviews: {has_reviews}"
            )

            data_job = self.client.query(data_query, job_config=job_config)
            count_job = self.client.query(count_query, job_config=job_config)

            data_results = data_job.result()
            count_results = count_job.result()

            # Build response objects
            sources = []
            for row in data_results:
                source_response = ReviewSourceResponse(
                    app_id=row["app_id"],
                    source=row["source"],
                    total_reviews=row["total_reviews"],
                    average_rating=round(row["average_rating"], 2),
                    first_review_date=row["first_review_date"],
                    last_review_date=row["last_review_date"],
                )
                sources.append(source_response)

            total = list(count_results)[0].total

            logger.info(f"Found {len(sources)} sources out of {total} total")
            return sources, total

        except Exception as e:
            logger.error(f"Error fetching review sources: {e}")
            raise DatabaseConnectionError(f"Error querying the database: {e}")

    async def get_reviews_by_app(
        self,
        app_id: str,
        skip: int = 0,
        limit: int = 20,
        rating_min: Optional[int] = None,
        rating_max: Optional[int] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        filter: Optional[str] = None,
    ) -> Tuple[List[Review], int, str, str]:
        """Get paginated reviews for a specific app with optional filters.

        Args:
            app_id: App ID to fetch reviews for
            skip: Number of records to skip (for pagination)
            limit: Maximum number of records to return
            rating_min: Minimum rating filter (1-5)
            rating_max: Maximum rating filter (1-5)
            date_from: Start date filter
            date_to: End date filter
            filter: Special filter - 'best' (rating > 2) or 'worst' (rating <= 2)

        Returns:
            Tuple containing (reviews list, total count, app_id, source)

        Raises:
            DatabaseConnectionError: If app_id doesn't exist or query fails
        """
        where_clauses = ["app_id = @app_id"]
        query_params = [bigquery.ScalarQueryParameter("app_id", "STRING", app_id)]

        if rating_min is not None:
            where_clauses.append("score >= @rating_min")
            query_params.append(
                bigquery.ScalarQueryParameter("rating_min", "INT64", rating_min)
            )

        if rating_max is not None:
            where_clauses.append("score <= @rating_max")
            query_params.append(
                bigquery.ScalarQueryParameter("rating_max", "INT64", rating_max)
            )

        if date_from is not None:
            where_clauses.append("fecha >= @date_from")
            query_params.append(
                bigquery.ScalarQueryParameter("date_from", "TIMESTAMP", date_from)
            )

        if date_to is not None:
            where_clauses.append("fecha <= @date_to")
            query_params.append(
                bigquery.ScalarQueryParameter("date_to", "TIMESTAMP", date_to)
            )

        # Handle special filter types
        order_clause = "ORDER BY fecha DESC"  # Default ordering
        if filter == "best":
            where_clauses.append("score >= 3")
            order_clause = "ORDER BY score DESC, fecha DESC"
        elif filter == "worst":
            where_clauses.append("score <= 2")
            order_clause = "ORDER BY score ASC, fecha DESC"

        where_clause = "WHERE " + " AND ".join(where_clauses)

        # First, check if app exists and get its source
        check_query = f"""
        SELECT LOWER(source) as source, COUNT(*) as count
        FROM `{self.table_id}`
        WHERE app_id = @app_id
        GROUP BY source
        LIMIT 1
        """

        # Data query
        data_query = f"""
        SELECT
            review_historico_id,
            app_id,
            fecha,
            content,
            score,
            LOWER(source) as source
        FROM `{self.table_id}`
        {where_clause}
        {order_clause}
        LIMIT @limit OFFSET @skip
        """

        # Count query
        count_query = f"""
        SELECT COUNT(*) as total
        FROM `{self.table_id}`
        {where_clause}
        """

        query_params.append(bigquery.ScalarQueryParameter("limit", "INT64", limit))
        query_params.append(bigquery.ScalarQueryParameter("skip", "INT64", skip))

        job_config = bigquery.QueryJobConfig(query_parameters=query_params)
        check_config = bigquery.QueryJobConfig(
            query_parameters=[bigquery.ScalarQueryParameter("app_id", "STRING", app_id)]
        )

        try:
            logger.info(
                f"Fetching reviews for app_id: {app_id} with filters - "
                f"rating: {rating_min}-{rating_max}, date: {date_from}-{date_to}, filter: {filter}"
            )

            # Check if app exists
            check_job = self.client.query(check_query, job_config=check_config)
            check_results = list(check_job.result())

            if not check_results:
                raise DatabaseConnectionError(f"App ID '{app_id}' not found")

            source = check_results[0]["source"]

            # Execute main queries
            data_job = self.client.query(data_query, job_config=job_config)
            count_job = self.client.query(count_query, job_config=job_config)

            data_results = data_job.result()
            count_results = count_job.result()

            # Build review objects
            reviews = []
            for row in data_results:
                review = Review(
                    review_id=row["review_historico_id"],
                    rating=row["score"],
                    comment=row["content"],
                    date=row["fecha"],
                )
                reviews.append(review)

            total = list(count_results)[0].total

            logger.info(
                f"Found {len(reviews)} reviews out of {total} total for app {app_id}"
            )
            return reviews, total, app_id, source

        except DatabaseConnectionError:
            raise
        except Exception as e:
            logger.error(f"Error fetching reviews for app {app_id}: {e}")
            raise DatabaseConnectionError(f"Error querying the database: {e}")

    async def get_reviews(
        self, skip: int = 0, limit: int = 10, app_id: Optional[str] = None
    ) -> tuple[List[ReviewResponse], int]:
        """Get all reviews grouped by app_id and source with pagination.

        DEPRECATED: This method groups all reviews which can lead to large response objects.
        Use get_review_sources() for listing apps and get_reviews_by_app() for individual app reviews.
        """
        base_query = f"""
        SELECT
            review_historico_id,
            app_id,
            fecha,
            content,
            score,
            source,
            created_at,
            updated_at
        FROM `{self.table_id}`
        """

        where_clause = ""
        query_params = []

        if app_id:
            where_clause = "WHERE app_id = @app_id"
            query_params.append(
                bigquery.ScalarQueryParameter("app_id", "STRING", app_id)
            )

        data_query = f"""
        {base_query}
        {where_clause}
        ORDER BY created_at DESC
        LIMIT @limit OFFSET @skip
        """

        count_query = f"""
        SELECT COUNT(DISTINCT CONCAT(app_id, '_', source)) as total
        FROM `{self.table_id}`
        {where_clause}
        """

        query_params.append(bigquery.ScalarQueryParameter("limit", "INT64", limit))
        query_params.append(bigquery.ScalarQueryParameter("skip", "INT64", skip))

        job_config = bigquery.QueryJobConfig(query_parameters=query_params)

        try:
            data_job = self.client.query(data_query, job_config=job_config)
            count_job = self.client.query(count_query, job_config=job_config)

            data_results = data_job.result()
            count_results = count_job.result()

            # Group reviews by app_id and source
            grouped_reviews = defaultdict(lambda: defaultdict(list))

            for row in data_results:
                review_data = dict(row)
                app_id_key = review_data["app_id"]
                source_key = review_data["source"]

                # Create Review object with expected format
                review = Review(
                    review_id=review_data["review_historico_id"],
                    rating=review_data["score"],
                    comment=review_data["content"],
                    date=review_data["fecha"],
                )

                grouped_reviews[app_id_key][source_key].append(review)

            # Convert to ReviewResponse list
            review_responses = []
            for app_id_key, sources in grouped_reviews.items():
                for source_key, reviews_list in sources.items():
                    review_response = ReviewResponse(
                        app_id=app_id_key, source=source_key, reviews=reviews_list
                    )
                    review_responses.append(review_response)

            total = list(count_results)[0].total

            return review_responses, total
        except Exception as e:
            raise DatabaseConnectionError(f"Error querying the database: {e}")

    async def get_metrics(
        self,
        app_id: str,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
    ) -> tuple[dict[str, int | float | None], dict[str, Optional[str]], str]:
        """Get metrics for a specific app.

        Args:
            app_id: App ID to fetch metrics for
            date_from: Start date for metrics
            date_to: End date for metrics

        Returns:
            Tuple containing:
            - metrics: Dictionary with keys:
                - average_rating: The average rating value (float or None)
                - total_reviews: The total number of reviews (int)
                - reviews_by_score: Dictionary mapping score to count of reviews
            - time_frame: Dictionary with date_from and date_to if provided
            - source: The source of the reviews
        """
        base_query = f"""
        SELECT
            source,
            AVG(score) as average_rating,
            count(*) as total_reviews
        FROM `{self.table_id}`
        WHERE app_id = @app_id
        """

        score_query = f"""
        SELECT
            score,
            COUNT(*) as review_count
        FROM `{self.table_id}`
        WHERE app_id = @app_id
        """

        time_frame = {}
        query_params = [bigquery.ScalarQueryParameter("app_id", "STRING", app_id)]

        if date_from is not None:
            date_filter = " AND fecha >= @date_from"
            base_query += date_filter
            score_query += date_filter
            query_params.append(
                bigquery.ScalarQueryParameter("date_from", "DATE", date_from.date())
            )
            time_frame["date_from"] = date_from.isoformat()

        if date_to is not None:
            date_filter = " AND fecha <= @date_to"
            base_query += date_filter
            score_query += date_filter
            query_params.append(
                bigquery.ScalarQueryParameter("date_to", "DATE", date_to.date())
            )
            time_frame["date_to"] = date_to.isoformat()

        base_query += " GROUP BY source"
        score_query += " GROUP BY score ORDER BY score"

        job_config = bigquery.QueryJobConfig(query_parameters=query_params)

        try:
            data_job = self.client.query(base_query, job_config=job_config)
            data_results = data_job.result()
            rows = list(data_results)

            score_job = self.client.query(score_query, job_config=job_config)
            score_results = score_job.result()

            reviews_by_score = {
                row["score"]: row["review_count"] for row in score_results
            }

            if not rows:
                metrics = {
                    "average_rating": None,
                    "total_reviews": 0,
                }
                return metrics, time_frame, "unknown"

            row = rows[0]
            metrics = {
                "average_rating": (
                    round(row["average_rating"], 2)
                    if row["average_rating"] is not None
                    else None
                ),
                "total_reviews": row["total_reviews"],
                "reviews_by_score": reviews_by_score,
            }

            return metrics, time_frame, row["source"]

        except Exception as e:
            raise DatabaseConnectionError(f"Error querying the database: {e}")

    async def get_latest_analysis(
        self,
        app_id: str,
    ) -> Optional[dict]:
        """
        Get the latest AI analysis for a specific app.

        Args:
            app_id (str): The ID of the app to fetch analysis for.
        Returns:
            Optional[dict]: The latest analysis data as a dictionary, or None if not found.
        """
        query = f"""
        SELECT
            json_data
        FROM `{self.analysis_table_id}`
        WHERE app_id = @app_id
        ORDER BY analyzed_at DESC
        LIMIT 1
        """

        query_params = [bigquery.ScalarQueryParameter("app_id", "STRING", app_id)]
        job_config = bigquery.QueryJobConfig(query_parameters=query_params)

        try:
            data_job = self.client.query(query, job_config=job_config)
            data_results = data_job.result()
            rows = list(data_results)

            if rows:
                json_data = rows[0]["json_data"]
                if isinstance(json_data, str):
                    return json.loads(json_data)
                return json_data
            return None

        except Exception as e:
            raise DatabaseConnectionError(f"Error querying the database: {e}")

    async def request_ai_analysis(
        self,
        app_id: str,
        analysis_params: Optional[AnalysisParameters] = None,
    ):
        """
        Request AI analysis for reviews of a specific app.
        Calls an external AI (OpenAI) service to perform the analysis using batch processing.

        Args:
            app_id (str): The ID of the app to analyze.
            analysis_params (Optional[AIAnalysisRequest]): The parameters for the analysis.
        """
        # 1. Obtain reviews for the app
        reviews = await self._get_reviews_for_analysis(app_id, analysis_params)

        logger.info(f"Fetched {len(reviews)} reviews for analysis of app_id: {app_id}")
        logger.info(f"Sample review: {reviews[0].comment if reviews else 'No reviews found'}")

        # 2. Call integration with AI service (OpenAI) to analyze reviews
        openai_integration = OpenAIBatchIntegration()

        reviews_data = [
            (review.comment, review.rating, review.date) for review in reviews
        ]

        file_uploaded, batch_object = openai_integration.process_using_batches(
            reviews_data
        )

        logger.info(
            f"Requested AI analysis for app_id: {app_id}, batch_id: {batch_object.id}"
        )
        return batch_object, file_uploaded

    async def _get_reviews_for_analysis(
        self,
        app_id: str,
        analysis_params: Optional[AnalysisParameters] = None,
    ) -> List[Review]:
        """Helper method to get reviews for AI analysis.

        Args:
            app_id: App ID to fetch reviews for
            analysis_params: Analysis parameters including filters
        """

        query = f"""
        SELECT
            review_historico_id,
            app_id,
            fecha,
            content,
            score,
            LOWER(source) as source
        FROM `{self.table_id}`
        WHERE app_id = @app_id
        """

        query_params = [bigquery.ScalarQueryParameter("app_id", "STRING", app_id)]

        if analysis_params:
            if analysis_params.min_rating is not None:
                query += " AND score >= @min_rating"
                query_params.append(
                    bigquery.ScalarQueryParameter(
                        "min_rating", "INT64", analysis_params.min_rating
                    )
                )

            if analysis_params.max_rating is not None:
                query += " AND score <= @max_rating"
                query_params.append(
                    bigquery.ScalarQueryParameter(
                        "max_rating", "INT64", analysis_params.max_rating
                    )
                )

            if analysis_params.from_date is not None:
                # Convert string to date object if needed
                from_date = analysis_params.from_date
                if isinstance(from_date, str):
                    from_date = datetime.fromisoformat(from_date).date()

                query += " AND fecha >= @from_date"
                query_params.append(
                    bigquery.ScalarQueryParameter("from_date", "DATE", from_date)
                )

            if analysis_params.to_date is not None:
                # Convert string to date object if needed
                to_date = analysis_params.to_date
                if isinstance(to_date, str):
                    to_date = datetime.fromisoformat(to_date).date()

                query += " AND fecha <= @to_date"
                query_params.append(
                    bigquery.ScalarQueryParameter("to_date", "DATE", to_date)
                )

        query += " ORDER BY fecha DESC"
        job_config = bigquery.QueryJobConfig(query_parameters=query_params)

        try:
            data_job = self.client.query(query, job_config=job_config)
            data_results = data_job.result()

            reviews = []
            for row in data_results:
                review = Review(
                    review_id=row["review_historico_id"],
                    rating=row["score"],
                    comment=row["content"],
                    date=row["fecha"],
                )
                reviews.append(review)

            return reviews
        except Exception as e:
            raise DatabaseConnectionError(f"Error querying the database: {e}")
    async def get_ai_analysis(self, app_id: str) -> Dict[str, Any]:
        """
        Get aggregated AI analysis for a specific app.
        
        This method fetches all AI analyses for an app from BigQuery,
        aggregates the data, and transforms it into the required response format.
        Only uses actual data from the analyses - does not generate synthetic content.
        
        Args:
            app_id: The ID of the app to fetch analysis for
            
        Returns:
            Dict containing aggregated analysis based on actual review data
        """
        
        # Query to fetch all analyses for the app
        query = f"""
        SELECT
            json_data,
            review_date,
            analyzed_at
        FROM `{self.analysis_table_id}`
        WHERE app_id = @app_id
        ORDER BY analyzed_at DESC
        """
        
        query_params = [bigquery.ScalarQueryParameter("app_id", "STRING", app_id)]
        job_config = bigquery.QueryJobConfig(query_parameters=query_params)
        
        try:
            # Execute query
            data_job = self.client.query(query, job_config=job_config)
            data_results = data_job.result()
            rows = list(data_results)
            
            if not rows:
                logger.warning(f"No AI analysis found for app_id: {app_id}")
                # Return minimal structure when no data exists
                return {
                    "sentimentSummary": {
                        "positive": 0,
                        "neutral": 0,
                        "negative": 0,
                        "description": "No hay análisis disponibles para esta aplicación."
                    },
                    "technicalIssues": [],
                    "strengths": [],
                    "weaknesses": [],
                    "recommendations": [],
                    "insights": [],
                    "volumeAnalyzed": 0
                }
            
            # Parse all JSON data
            analyses = []
            for row in rows:
                json_data = row["json_data"]
                if isinstance(json_data, str):
                    analyses.append(json.loads(json_data))
                else:
                    analyses.append(json_data)
            
            # Aggregate data using only actual content from analyses
            aggregated_data = self._aggregate_analyses(analyses)
            
            return aggregated_data
            
        except Exception as e:
            logger.error(f"Error fetching AI analysis for app {app_id}: {e}")
            raise DatabaseConnectionError(f"Error querying the database: {e}")
        
    def _aggregate_analyses(self, analyses: List[Dict]) -> Dict[str, Any]:
        """
        Aggregate multiple ReviewAnalysis objects into the desired response format.
        Only uses actual data present in the analyses - no synthetic generation.
        
        Args:
            analyses: List of parsed ReviewAnalysis JSON objects
            
        Returns:
            Aggregated analysis in the required format
        """
        
        # Initialize counters and collectors
        sentiment_counts = Counter()
        all_descriptions = []
        technical_issues_map = defaultdict(int)
        strengths_texts = []
        weaknesses_texts = []
        recommendations_data = []
        insights_data = []
        total_reviews = len(analyses)
        
        # Process each analysis - only extract what actually exists
        for analysis in analyses:
            # Sentiment aggregation
            if 'sentimentSummary' in analysis:
                sentiment = analysis['sentimentSummary'].get('overall')
                if sentiment:
                    sentiment_counts[sentiment] += 1
                
                description = analysis['sentimentSummary'].get('description')
                if description:
                    all_descriptions.append(description)
            
            # Technical issues - extract actual issue text
            if 'technicalIssues' in analysis and analysis['technicalIssues']:
                for issue in analysis['technicalIssues']:
                    issue_text = issue.get('issue')
                    if issue_text:
                        technical_issues_map[issue_text] += 1
            
            # Strengths - extract feature names
            if 'strengths' in analysis and analysis['strengths']:
                for strength in analysis['strengths']:
                    feature = strength.get('feature')
                    if feature:
                        strengths_texts.append(feature)
            
            # Weaknesses - extract aspect names  
            if 'weaknesses' in analysis and analysis['weaknesses']:
                for weakness in analysis['weaknesses']:
                    aspect = weakness.get('aspect')
                    if aspect:
                        weaknesses_texts.append(aspect)
            
            # Recommendations - extract actual recommendation data
            if 'recommendations' in analysis and analysis['recommendations']:
                for rec in analysis['recommendations']:
                    # Only include if it has both action and priority
                    action = rec.get('action')
                    priority = rec.get('priority')
                    category = rec.get('category')
                    
                    if action and (priority in ['critical', 'high']):
                        recommendations_data.append({
                            'action': action,
                            'category': category,
                            'priority': priority,
                            'expectedImpact': rec.get('expectedImpact', '')
                        })
            
            # Insights - extract actual insight data
            if 'insights' in analysis and analysis['insights']:
                for insight in analysis['insights']:
                    observation = insight.get('observation')
                    insight_type = insight.get('type')
                    if observation and insight_type:
                        insights_data.append({
                            'observation': observation,
                            'type': insight_type
                        })
        
        # Build response with only available data
        response = {}
        
        # Calculate sentiment percentages if we have sentiment data
        if sentiment_counts:
            total_sentiments = sum(sentiment_counts.values())
            sentiment_percentages = {}
            
            # Calculate percentages for sentiments that exist
            for sentiment in ['positive', 'neutral', 'negative']:
                count = sentiment_counts.get(sentiment, 0)
                sentiment_percentages[sentiment] = round((count / total_sentiments) * 100) if total_sentiments > 0 else 0
            
            # Use the first available description or create a simple one based on data
            description = all_descriptions[0] if all_descriptions else self._create_simple_description(sentiment_percentages)
            
            response["sentimentSummary"] = {
                "positive": sentiment_percentages.get("positive", 0),
                "neutral": sentiment_percentages.get("neutral", 0),
                "negative": sentiment_percentages.get("negative", 0),
                "description": description
            }
        
        # Format technical issues with percentages if we have them
        if technical_issues_map:
            technical_issues_formatted = []
            # Get top issues sorted by frequency
            top_issues = sorted(
                technical_issues_map.items(), 
                key=lambda x: x[1], 
                reverse=True
            )[:5]  # Limit to top 5
            
            total_issue_mentions = sum(technical_issues_map.values())
            for issue_text, count in top_issues:
                percentage = round((count / total_issue_mentions) * 100) if total_issue_mentions > 0 else 0
                technical_issues_formatted.append({
                    "topic": issue_text[:60],  # Truncate if too long
                    "percentage": percentage
                })
            
            response["technicalIssues"] = technical_issues_formatted
        
        # Get most common strengths (unique values)
        if strengths_texts:
            strength_counts = Counter(strengths_texts)
            response["strengths"] = [strength for strength, _ in strength_counts.most_common(5)]
        
        # Get most common weaknesses (unique values)
        if weaknesses_texts:
            weakness_counts = Counter(weaknesses_texts)
            response["weaknesses"] = [weakness for weakness, _ in weakness_counts.most_common(5)]
        
        # Format recommendations if available
        if recommendations_data:
            # Group by action to avoid duplicates
            unique_recommendations = {}
            for rec_data in recommendations_data:
                action = rec_data['action']
                if action not in unique_recommendations:
                    unique_recommendations[action] = rec_data
            
            # Format for response - create issue/solution pairs from actual data
            formatted_recommendations = []
            for action, rec_data in list(unique_recommendations.items())[:5]:  # Limit to 5
                # Extract issue from action or category context
                issue = self._extract_issue_from_recommendation(rec_data)
                formatted_recommendations.append({
                    "issue": issue,
                    "solution": action
                })
            
            response["recommendations"] = formatted_recommendations
        
        # Format insights if available - using actual observation data
        if insights_data:
            # Group insights by type to identify trends
            insights_by_type = defaultdict(list)
            for insight in insights_data:
                insights_by_type[insight['type']].append(insight['observation'])
            
            formatted_insights = []
            for insight_type, observations in insights_by_type.items():
                if len(observations) >= 2:  # Only report if it's a trend (appears multiple times)
                    # Determine if positive or negative based on type
                    trend_type = self._determine_trend_type(insight_type)
                    
                    # Use the most common observation as the trend description
                    observation_counts = Counter(observations)
                    most_common_observation = observation_counts.most_common(1)[0][0]
                    
                    formatted_insights.append({
                        "trend": most_common_observation,
                        "type": trend_type
                    })
            
            if formatted_insights:
                response["insights"] = formatted_insights[:5]  # Limit to 5
        
        # Always include volume analyzed
        response["volumeAnalyzed"] = total_reviews
        
        # Ensure all expected fields are present (even if empty)
        response.setdefault("sentimentSummary", {
            "positive": 0,
            "neutral": 0, 
            "negative": 0,
            "description": "Sin datos de sentimiento disponibles"
        })
        response.setdefault("technicalIssues", [])
        response.setdefault("strengths", [])
        response.setdefault("weaknesses", [])
        response.setdefault("recommendations", [])
        response.setdefault("insights", [])
        
        return response
            
    def _create_simple_description(self, percentages: Dict[str, int]) -> str:
        """
        Create a simple sentiment description based on percentages.
        Only uses actual data, no embellishment.
        """
        dominant = max(percentages.items(), key=lambda x: x[1])
        
        if dominant[0] == 'positive' and dominant[1] > 50:
            return f"Mayoría de reseñas positivas ({dominant[1]}%)"
        elif dominant[0] == 'negative' and dominant[1] > 50:
            return f"Mayoría de reseñas negativas ({dominant[1]}%)"
        elif dominant[0] == 'neutral' and dominant[1] > 50:
            return f"Mayoría de reseñas neutrales ({dominant[1]}%)"
        else:
            return "Opiniones mixtas en las reseñas" 
        
    def _extract_issue_from_recommendation(self, rec_data: Dict) -> str:
        """
        Extract or infer the issue from recommendation data.
        Uses only actual data from the recommendation.
        """
        # Try to extract from action text
        action = rec_data.get('action', '')
        category = rec_data.get('category', '')
        
        # Look for keywords in action to identify the issue
        action_lower = action.lower()
        
        if 'fix' in action_lower or 'arreglar' in action_lower:
            # Extract what needs to be fixed
            parts = action.split()
            if len(parts) > 2:
                return ' '.join(parts[1:4])  # Get the next few words after "fix"
        
        if 'optimizar' in action_lower or 'optimize' in action_lower:
            return "Problemas de rendimiento"
        
        if 'actualizar' in action_lower or 'update' in action_lower:
            return "Componentes desactualizados"
        
        # Use category as fallback
        category_issues = {
            'technical': 'Problema técnico',
            'performance': 'Problema de rendimiento',
            'ux_design': 'Problema de diseño',
            'feature': 'Funcionalidad faltante',
            'content': 'Problema de contenido'
        }
        
        return category_issues.get(category, 'Área de mejora identificada')
    
    def _determine_trend_type(self, insight_type: str) -> str:
        """
        Determine if an insight type represents a positive or negative trend.
        Based on the actual InsightType enum from review_model_response.py
        """
        positive_types = ['SATISFACTION_DRIVER', 'USER_SEGMENT']
        negative_types = ['ADOPTION_BARRIER', 'CHURN_RISK', 'FEATURE_GAP']
        
        if insight_type in positive_types:
            return "positive"
        elif insight_type in negative_types:
            return "negative"
        else:
            return "neutral"
        
review_service = ReviewService()
