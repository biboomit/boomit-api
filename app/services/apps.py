from typing import Optional, List, Dict, Any
from google.cloud import bigquery
from app.core.exceptions import DatabaseConnectionError
from app.schemas.apps import AppDetailsResponse
from app.core.config import bigquery_config
from datetime import datetime, date, timedelta
import logging
import httpx
import os

logger = logging.getLogger(__name__)


class AppService:
    # Class constants for default values
    DEFAULT_DEVELOPER = 'Unknown Developer'
    DEFAULT_CATEGORY = 'Unknown Category'
    DEFAULT_ICON_URL = ''
    DEFAULT_DOWNLOADS = 0
    
    # Cloud Run scraper endpoints - Required environment variables (fail-fast if not set)
    ANDROID_SCRAPER_URL = os.environ["ANDROID_SCRAPER_URL"]s
    IOS_SCRAPER_URL = os.environ["IOS_SCRAPER_URL"]
    
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
        Call Cloud Run scraper to scrape and insert app data into BigQuery.
        
        Args:
            app_id: App ID to scrape
            store: Store type ('android' or 'ios')
            country: Country code
            
        Returns:
            AppDetailsResponse with app details from database
            
        Raises:
            ValueError: If scraping fails or store is invalid
        """
        store_lower = store.lower()
        
        # Select appropriate scraper URL
        if store_lower == 'android':
            scraper_url = f"{self.ANDROID_SCRAPER_URL}/scrape"
        elif store_lower == 'ios':
            scraper_url = f"{self.IOS_SCRAPER_URL}/scrape"
        else:
            raise ValueError(f"Invalid store type: {store}. Must be 'android' or 'ios'")
        
        try:
            # Call Cloud Run scraper
            logger.info(f"Calling {store} scraper for app: {app_id}")
            
            async with httpx.AsyncClient(timeout=300.0) as client:
                response = await client.post(
                    scraper_url,
                    json={"app_id": app_id, "country": country}
                )
                
                if response.status_code == 404:
                    raise ValueError(f"App '{app_id}' not found in {store} store")
                
                if response.status_code != 200:
                    error_msg = response.json().get('error', 'Unknown error')
                    raise ValueError(f"Scraper error: {error_msg}")
                
                result = response.json()
                logger.info(f"Scraper response: {result}")
            
            # Now fetch the app from database (scraper already inserted it)
            app = await self._get_app_by_id(app_id, store_lower, country)
            
            if not app:
                raise ValueError(f"App was scraped but not found in database: {app_id}")
            
            return app
            
        except httpx.HTTPError as e:
            logger.error(f"HTTP error calling scraper for {app_id}: {e}")
            raise ValueError(f"Failed to call scraper service: {str(e)}")
        except Exception as e:
            logger.error(f"Error scraping app {app_id}: {e}")
            raise ValueError(f"Failed to scrape app '{app_id}': {str(e)}")


# Singleton instance
app_service = AppService()