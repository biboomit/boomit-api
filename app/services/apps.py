from typing import Optional, List, Dict, Any
from google.cloud import bigquery
from app.core.exceptions import DatabaseConnectionError
from app.schemas.apps import AppDetailsResponse
from app.core.config import bigquery_config
from app.integrations.scrapers.google_play import google_play_scraper
from app.integrations.scrapers.app_store import app_store_scraper
from datetime import datetime, date, timedelta
import logging
import uuid

logger = logging.getLogger(__name__)


class AppService:
    # Class constants for default values
    DEFAULT_DEVELOPER = 'Unknown Developer'
    DEFAULT_CATEGORY = 'Unknown Category'
    DEFAULT_ICON_URL = ''
    DEFAULT_DOWNLOADS = 0
    
    def __init__(self) -> None:
        self.client = bigquery_config.get_client()
        self.maestro_table = bigquery_config.get_table_id("DIM_MAESTRO_REVIEWS")
        self.historico_table = bigquery_config.get_table_id("DIM_REVIEWS_HISTORICO")

    async def search_apps(
        self,
        app_name: str,
        store: Optional[str] = None,
        country: Optional[str] = None
    ) -> List[AppDetailsResponse]:
        """Search for apps by name with optional filters.

        Args:
            app_name: Name to search for (partial matching)
            store: Optional store filter (android/ios)
            country: Optional country filter

        Returns:
            List of AppDetailsResponse objects

        Raises:
            DatabaseConnectionError: If query fails
        """
        
        # Construir condiciones WHERE dinámicamente
        where_conditions = ["LOWER(app_name) LIKE @app_name"]
        query_params = [
            bigquery.ScalarQueryParameter("app_name", "STRING", f"%{app_name.lower()}%")
        ]

        if store:
            where_conditions.append("LOWER(SO) = @store")
            query_params.append(
                bigquery.ScalarQueryParameter("store", "STRING", store.lower())
            )

        if country:
            where_conditions.append("LOWER(country_code) = @country")
            query_params.append(
                bigquery.ScalarQueryParameter("country", "STRING", country.lower())
            )

        where_clause = "WHERE " + " AND ".join(where_conditions)

        # Query principal para obtener datos de las apps
        main_query = f"""
        SELECT DISTINCT
            m.app_id,
            m.app_name,
            LOWER(m.SO) as store,
            COALESCE(m.app_desarrollador, '{self.DEFAULT_DEVELOPER}') as developer,
            COALESCE(m.app_descargas, {self.DEFAULT_DOWNLOADS}) as downloads,
            COALESCE(m.app_icon_url, '{self.DEFAULT_ICON_URL}') as icon_url,
            COALESCE(m.app_categoria, '{self.DEFAULT_CATEGORY}') as category,
            COALESCE(m.fecha_actualizacion, CURRENT_DATE()) as last_update
        FROM `{self.maestro_table}` m
        {where_clause}
        ORDER BY downloads DESC, app_name ASC
        """

        job_config = bigquery.QueryJobConfig(query_parameters=query_params)

        try:
            logger.info(f"Searching apps with name: '{app_name}', store: {store}, country: {country}")

            # Ejecutar query principal
            main_job = self.client.query(main_query, job_config=job_config)
            main_results = list(main_job.result())

            if not main_results:
                logger.info(f"No apps found for search: '{app_name}'")
                return []

            # Extract app_ids for batch rating query
            app_ids = [row.app_id for row in main_results]
            
            # Get ratings for all apps in a single batch query
            ratings_data = await self._get_batch_app_ratings(app_ids)

            # Procesar resultados y crear objetos de respuesta
            apps = []
            for row in main_results:
                # Get ratings for this app from batch results
                app_rating_data = ratings_data.get(row.app_id, {
                    'average_rating': None,
                    'total_ratings': 0
                })
                
                # Procesar fecha de actualización
                last_update = row.last_update
                if isinstance(last_update, datetime):
                    last_update = last_update.date()
                elif last_update is None:
                    last_update = date.today()

                # Crear objeto AppDetailsResponse
                app = AppDetailsResponse(
                    app_id=row.app_id,
                    app_name=row.app_name,
                    store=row.store,
                    developer=row.developer,
                    rating_average=app_rating_data.get('average_rating'),
                    total_ratings=app_rating_data.get('total_ratings'),
                    downloads=row.downloads,
                    last_update=last_update,
                    icon_url=row.icon_url,
                    category=row.category
                )
                apps.append(app)

            logger.info(f"Found {len(apps)} apps for search: '{app_name}'")
            return apps

        except Exception as e:
            logger.error(f"Error searching apps for '{app_name}': {e}")
            raise DatabaseConnectionError(f"Error querying the database: {e}")

    async def _get_app_ratings(self, app_id: str) -> dict:
        """Get rating information for a specific app.

        Args:
            app_id: App ID to get ratings for

        Returns:
            Dictionary with 'average_rating' and 'total_ratings'
        """
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
            ratings_job = self.client.query(ratings_query, job_config=job_config)
            ratings_results = list(ratings_job.result())

            if ratings_results and ratings_results[0].total_ratings > 0:
                rating_data = ratings_results[0]
                return {
                    'average_rating': round(rating_data.average_rating, 2) if rating_data.average_rating else None,
                    'total_ratings': rating_data.total_ratings
                }
            else:
                return {
                    'average_rating': None,
                    'total_ratings': None
                }

        except Exception as e:
            logger.warning(f"Error getting ratings for app {app_id}: {e}")
            return {
                'average_rating': None,
                'total_ratings': None
            }

    async def _get_batch_app_ratings(self, app_ids: List[str]) -> dict:
        """Get rating information for multiple apps in a single query.
        
        Args:
            app_ids: List of app IDs to get ratings for
            
        Returns:
            Dictionary mapping app_id to rating data: {app_id: {'average_rating': float, 'total_ratings': int}}
        """
        if not app_ids:
            return {}
            
        try:
            logger.debug(f"Getting ratings for {len(app_ids)} apps in batch")
            
            # Create batch ratings query
            ratings_query = f"""
            SELECT
                app_id,
                AVG(CAST(score AS FLOAT64)) as average_rating,
                COUNT(*) as total_ratings
            FROM `{self.historico_table}`
            WHERE app_id IN UNNEST(@app_ids)
            AND score IS NOT NULL 
            AND score > 0
            GROUP BY app_id
            """
            
            job_config = bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ArrayQueryParameter("app_ids", "STRING", app_ids)
                ]
            )
            
            ratings_job = self.client.query(ratings_query, job_config=job_config)
            ratings_results = list(ratings_job.result())
            
            # Process results into dictionary
            ratings_dict = {}
            for row in ratings_results:
                if row.total_ratings and row.total_ratings > 0 and row.average_rating is not None:
                    ratings_dict[row.app_id] = {
                        'average_rating': round(float(row.average_rating), 2),
                        'total_ratings': int(row.total_ratings)
                    }
                else:
                    ratings_dict[row.app_id] = {
                        'average_rating': None,
                        'total_ratings': 0
                    }
            
            # Ensure all requested app_ids have entries (even if no ratings found)
            for app_id in app_ids:
                if app_id not in ratings_dict:
                    ratings_dict[app_id] = {
                        'average_rating': None,
                        'total_ratings': 0
                    }
            
            logger.debug(f"Successfully retrieved ratings for {len(ratings_dict)} apps")
            return ratings_dict
            
        except Exception as e:
            logger.warning(f"Error getting batch ratings for apps: {e}")
            # Return empty dict for all apps if batch query fails
            return {app_id: {'average_rating': None, 'total_ratings': 0} for app_id in app_ids}

    async def get_app_details(self, app_id: str) -> Optional[AppDetailsResponse]:
        """Get details for a specific app by ID"""
        try:
            logger.info(f"Getting details for app: {app_id}")
            
            # Query to get app details from maestro table
            query = f"""
                SELECT 
                    app_id,
                    app_name,
                    LOWER(SO) as store,
                    COALESCE(app_desarrollador, '{self.DEFAULT_DEVELOPER}') as developer,
                    COALESCE(app_descargas, {self.DEFAULT_DOWNLOADS}) as downloads,
                    COALESCE(app_icon_url, '{self.DEFAULT_ICON_URL}') as icon_url,
                    COALESCE(app_categoria, '{self.DEFAULT_CATEGORY}') as category,
                    COALESCE(fecha_actualizacion, CURRENT_DATE()) as last_update
                FROM `{self.maestro_table}`
                WHERE LOWER(app_id) = LOWER(@app_id)
                LIMIT 1
            """
            
            job_config = bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ScalarQueryParameter("app_id", "STRING", app_id)
                ]
            )
            
            result = self.client.query(query, job_config=job_config)
            rows = list(result)
            
            if not rows:
                logger.warning(f"App not found: {app_id}")
                return None
            
            row = rows[0]
            
            # Get ratings for this app
            ratings = await self._get_app_ratings(app_id)
            
            # Process last_update to ensure it's a date object
            last_update = row.last_update
            if isinstance(last_update, datetime):
                last_update = last_update.date()
            elif last_update is None:
                last_update = date.today()
            
            # Create app data dict with correct field mapping
            app_data = {
                'app_id': row.app_id,
                'app_name': row.app_name,
                'store': row.store,
                'developer': row.developer,
                'downloads': row.downloads,
                'icon_url': row.icon_url,
                'category': row.category,
                'last_update': last_update,
                'rating_average': ratings.get('average_rating'),  # Correct field name
                'total_ratings': ratings.get('total_ratings')
            }
            
            return AppDetailsResponse(**app_data)
            
        except Exception as e:
            logger.error(f"Error getting app details for {app_id}: {e}")
            raise DatabaseConnectionError(f"Error querying the database: {e}")

    async def get_or_create_app(
        self,
        app_id: str,
        store: str,
        country: str
    ) -> AppDetailsResponse:
        """
        Get app from database or scrape and create if it doesn't exist.
        
        Args:
            app_id: App ID to search for
            store: Store type ('android' or 'ios')
            country: Country code
            
        Returns:
            AppDetailsResponse with app details
            
        Raises:
            DatabaseConnectionError: If database operations fail
            ValueError: If scraping fails or store is invalid
        """
        try:
            # First, try to get from database
            logger.info(f"Searching for app in database: {app_id}")
            existing_app = await self._get_app_by_id(app_id, store, country)
            
            if existing_app:
                logger.info(f"App found in database: {app_id}")
                return existing_app
            
            # App not found, scrape and insert
            logger.info(f"App not found in database, scraping: {app_id}")
            app_details = await self._scrape_and_insert_app(app_id, store, country)
            
            return app_details
            
        except ValueError as ve:
            # Scraping errors (app not found in store, etc.)
            logger.error(f"Scraping error for app {app_id}: {ve}")
            raise
        except Exception as e:
            logger.error(f"Error in get_or_create_app for {app_id}: {e}")
            raise DatabaseConnectionError(f"Error processing app request: {e}")
    
    async def _get_app_by_id(
        self,
        app_id: str,
        store: str,
        country: str
    ) -> Optional[AppDetailsResponse]:
        """
        Get app from database by app_id, store, and country.
        
        Args:
            app_id: App ID to search for
            store: Store type ('android' or 'ios')
            country: Country code
            
        Returns:
            AppDetailsResponse if found, None otherwise
        """
        query = f"""
        SELECT 
            app_id,
            app_name,
            LOWER(SO) as store,
            COALESCE(app_desarrollador, '{self.DEFAULT_DEVELOPER}') as developer,
            COALESCE(app_descargas, {self.DEFAULT_DOWNLOADS}) as downloads,
            COALESCE(app_icon_url, '{self.DEFAULT_ICON_URL}') as icon_url,
            COALESCE(app_categoria, '{self.DEFAULT_CATEGORY}') as category,
            COALESCE(fecha_actualizacion, CURRENT_DATE()) as last_update
        FROM `{self.maestro_table}`
        WHERE LOWER(app_id) = LOWER(@app_id)
          AND LOWER(SO) = LOWER(@store)
          AND LOWER(country_code) = LOWER(@country)
        LIMIT 1
        """
        
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("app_id", "STRING", app_id),
                bigquery.ScalarQueryParameter("store", "STRING", store),
                bigquery.ScalarQueryParameter("country", "STRING", country),
            ]
        )
        
        try:
            result = self.client.query(query, job_config=job_config)
            rows = list(result)
            
            if not rows:
                return None
            
            row = rows[0]
            
            # Get ratings for this app
            ratings = await self._get_app_ratings(app_id)
            
            # Process last_update
            last_update = row.last_update
            if isinstance(last_update, datetime):
                last_update = last_update.date()
            elif last_update is None:
                last_update = date.today()
            
            return AppDetailsResponse(
                app_id=row.app_id,
                app_name=row.app_name,
                store=row.store,
                developer=row.developer,
                downloads=row.downloads,
                icon_url=row.icon_url,
                category=row.category,
                last_update=last_update,
                rating_average=ratings.get('average_rating'),
                total_ratings=ratings.get('total_ratings')
            )
            
        except Exception as e:
            logger.error(f"Error querying app {app_id}: {e}")
            raise DatabaseConnectionError(f"Error querying database: {e}")
    
    async def _scrape_and_insert_app(
        self,
        app_id: str,
        store: str,
        country: str
    ) -> AppDetailsResponse:
        """
        Scrape app data from store and insert into database.
        
        Args:
            app_id: App ID to scrape
            store: Store type ('android' or 'ios')
            country: Country code
            
        Returns:
            AppDetailsResponse with scraped app details
            
        Raises:
            ValueError: If scraping fails or store is invalid
        """
        store_lower = store.lower()
        
        # Select appropriate scraper
        if store_lower == 'android':
            scraper = google_play_scraper
        elif store_lower == 'ios':
            scraper = app_store_scraper
        else:
            raise ValueError(f"Invalid store type: {store}. Must be 'android' or 'ios'")
        
        try:
            # Scrape app metadata
            logger.info(f"Scraping app data from {store}: {app_id}")
            raw_app_data = scraper.fetch_app_data(app_id, country)
            app_info = scraper.extract_app_info(raw_app_data)
            
            # Insert into DIM_MAESTRO_REVIEWS
            await self._insert_app_to_maestro(app_id, store_lower, country, app_info)
            
            # Scrape and insert reviews (last 7 days, only if no reviews exist)
            await self._scrape_and_insert_reviews(app_id, store_lower, country, scraper)
            
            # Get ratings after inserting reviews
            ratings = await self._get_app_ratings(app_id)
            
            # Return app details
            return AppDetailsResponse(
                app_id=app_id,
                app_name=app_info['app_name'],
                store=store_lower,
                developer=app_info['app_desarrollador'],
                downloads=app_info['app_descargas'],
                icon_url=app_info['app_icon_url'],
                category=app_info['app_categoria'],
                last_update=date.today(),
                rating_average=ratings.get('average_rating') or app_info.get('rating_average'),
                total_ratings=ratings.get('total_ratings') or app_info.get('total_ratings', 0)
            )
            
        except Exception as e:
            logger.error(f"Error scraping app {app_id}: {e}")
            raise ValueError(f"Failed to scrape app '{app_id}': {str(e)}")
    
    async def _insert_app_to_maestro(
        self,
        app_id: str,
        store: str,
        country: str,
        app_info: Dict[str, Any]
    ) -> None:
        """
        Insert app metadata into DIM_MAESTRO_REVIEWS table.
        
        Args:
            app_id: App ID
            store: Store type
            country: Country code
            app_info: Dictionary with app information
        """
        # Generate review_id as combination of app_id + SO + country_code
        review_id = f"{app_id}_{store}_{country}"
        
        now = datetime.now()
        
        # Prepare row data
        row_data = {
            'review_id': review_id,
            'empresa_id': None,  # TODO: To be defined
            'canal_id': None,    # TODO: To be defined
            'app_id': app_id,
            'app_name': app_info['app_name'],
            'SO': store,
            'lang_code': 'es',  # Default Spanish
            'country_code': country,
            'app_descargas': app_info['app_descargas'],
            'app_desarrollador': app_info['app_desarrollador'],
            'app_categoria': app_info['app_categoria'],
            'app_icon_url': app_info['app_icon_url'],
            'fecha_creacion': now,
            'fecha_actualizacion': now,
        }
        
        try:
            logger.info(f"Inserting app into DIM_MAESTRO_REVIEWS: {app_id}")
            
            # Insert row
            errors = self.client.insert_rows_json(self.maestro_table, [row_data])
            
            if errors:
                logger.error(f"Errors inserting app {app_id}: {errors}")
                raise DatabaseConnectionError(f"Failed to insert app: {errors}")
            
            logger.info(f"Successfully inserted app {app_id} into DIM_MAESTRO_REVIEWS")
            
        except Exception as e:
            logger.error(f"Error inserting app {app_id}: {e}")
            raise DatabaseConnectionError(f"Database insert error: {e}")
    
    async def _scrape_and_insert_reviews(
        self,
        app_id: str,
        store: str,
        country: str,
        scraper: Any,
        days: int = 7
    ) -> None:
        """
        Scrape and insert reviews for an app (last N days, only new reviews).
        
        Args:
            app_id: App ID
            store: Store type
            country: Country code
            scraper: Scraper instance to use
            days: Number of days to look back (default: 7)
        """
        try:
            # Check if reviews already exist for this app
            existing_reviews_count = await self._count_existing_reviews(app_id)
            
            if existing_reviews_count > 0:
                logger.info(f"App {app_id} already has {existing_reviews_count} reviews, skipping scraping")
                return
            
            # Scrape reviews from last N days
            logger.info(f"Scraping reviews for {app_id} from last {days} days")
            reviews = scraper.fetch_recent_reviews(app_id, country, days)
            
            if not reviews:
                logger.info(f"No reviews found for {app_id}")
                return
            
            # Get existing review dates to avoid duplicates
            existing_dates = await self._get_existing_review_dates(app_id)
            
            # Filter out reviews that already exist
            new_reviews = []
            now = datetime.now()
            
            for review in reviews:
                review_date = review['at']
                review_content = review['content']
                
                # Check if review already exists (by date and content)
                if not self._review_exists(existing_dates, review_date, review_content):
                    review_id = str(uuid.uuid4())
                    
                    new_reviews.append({
                        'review_historico_id': review_id,
                        'app_id': app_id,
                        'fecha': review_date,
                        'content': review_content,
                        'score': review['score'],
                        'source': review['source'],
                        'created_at': now,
                        'updated_at': now,
                    })
            
            if not new_reviews:
                logger.info(f"No new reviews to insert for {app_id}")
                return
            
            # Insert reviews in batches
            logger.info(f"Inserting {len(new_reviews)} new reviews for {app_id}")
            errors = self.client.insert_rows_json(self.historico_table, new_reviews)
            
            if errors:
                logger.error(f"Errors inserting reviews for {app_id}: {errors}")
                raise DatabaseConnectionError(f"Failed to insert reviews: {errors}")
            
            logger.info(f"Successfully inserted {len(new_reviews)} reviews for {app_id}")
            
        except Exception as e:
            logger.error(f"Error scraping/inserting reviews for {app_id}: {e}")
            # Don't raise here - reviews are optional, app metadata is more important
            logger.warning(f"Continuing without reviews for {app_id}")
    
    async def _count_existing_reviews(self, app_id: str) -> int:
        """Count existing reviews for an app."""
        query = f"""
        SELECT COUNT(*) as count
        FROM `{self.historico_table}`
        WHERE app_id = @app_id
        """
        
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("app_id", "STRING", app_id)
            ]
        )
        
        try:
            result = self.client.query(query, job_config=job_config)
            rows = list(result)
            return rows[0].count if rows else 0
        except Exception as e:
            logger.error(f"Error counting reviews for {app_id}: {e}")
            return 0
    
    async def _get_existing_review_dates(self, app_id: str) -> List[Dict[str, Any]]:
        """Get existing review dates and content hashes for duplicate detection."""
        query = f"""
        SELECT fecha, content
        FROM `{self.historico_table}`
        WHERE app_id = @app_id
        """
        
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("app_id", "STRING", app_id)
            ]
        )
        
        try:
            result = self.client.query(query, job_config=job_config)
            return [{'fecha': row.fecha, 'content': row.content} for row in result]
        except Exception as e:
            logger.error(f"Error getting existing review dates for {app_id}: {e}")
            return []
    
    def _review_exists(
        self,
        existing_reviews: List[Dict[str, Any]],
        review_date: date,
        review_content: str
    ) -> bool:
        """Check if a review already exists based on date and content."""
        for existing in existing_reviews:
            if existing['fecha'] == review_date and existing['content'] == review_content:
                return True
        return False


# Singleton instance
app_service = AppService()