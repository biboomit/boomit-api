from typing import List, Optional
from google.cloud import bigquery
from app.core.exceptions import DatabaseConnectionError
from app.schemas.reviews import ReviewResponse, Review
from app.core.config import bigquery_config
from collections import defaultdict

class ReviewService:
    def __init__(self) -> None:
        self.client = bigquery_config.get_client()
        self.table_id = bigquery_config.get_table_id("DIM_REVIEWS_HISTORICO")

    async def get_reviews(
        self, skip: int = 0, limit: int = 10, app_id: Optional[str] = None
    ) -> tuple[List[ReviewResponse], int]:
        """Get all reviews grouped by app_id and source with pagination"""
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

            # Agrupar reviews por app_id y source
            grouped_reviews = defaultdict(lambda: defaultdict(list))

            for row in data_results:
                review_data = dict(row)
                app_id_key = review_data['app_id']
                source_key = review_data['source']

                # Crear objeto Review con el formato esperado
                review = Review(
                    review_id=review_data['review_historico_id'],
                    rating=review_data['score'],
                    comment=review_data['content'],
                    date=review_data['fecha']
                )

                grouped_reviews[app_id_key][source_key].append(review)

            # Convertir a lista de ReviewResponse
            review_responses = []
            for app_id_key, sources in grouped_reviews.items():
                for source_key, reviews_list in sources.items():
                    review_response = ReviewResponse(
                        app_id=app_id_key,
                        source=source_key,
                        reviews=reviews_list
                    )
                    review_responses.append(review_response)

            total = list(count_results)[0].total

            return review_responses, total
        except Exception as e:
            raise DatabaseConnectionError(f"Error querying the database: {e}")
        
review_service = ReviewService()