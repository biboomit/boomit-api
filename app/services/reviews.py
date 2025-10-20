from typing import List, Optional, Tuple
from google.cloud import bigquery
from app.core.exceptions import DatabaseConnectionError
from app.schemas.reviews import ReviewResponse, Review, ReviewSourceResponse
from app.core.config import bigquery_config
from collections import defaultdict
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class ReviewService:
    def __init__(self) -> None:
        self.client = bigquery_config.get_client()
        self.table_id = bigquery_config.get_table_id("DIM_REVIEWS_HISTORICO")

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
        ORDER BY fecha DESC
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
                f"rating: {rating_min}-{rating_max}, date: {date_from}-{date_to}"
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
    ) -> tuple[
        dict[str, int | float | None], dict[str, Optional[str]], str
    ]:
        """Get metrics for a specific app.

        Args:
            app_id: App ID to fetch metrics for
            date_from: Start date for metrics
            date_to: End date for metrics

        Returns:
            Tuple containing:
            - metrics: Dictionary with average_rating and total_reviews
            - time_frame: Dictionary with date_from and date_to if provided
            - source: The source of the reviews
            - reviews_by_score: Dictionary mapping score to count of reviews
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


review_service = ReviewService()
