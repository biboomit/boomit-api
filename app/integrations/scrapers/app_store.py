"""App Store scraper integration using app-store-scraper library."""

import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from app_store_scraper import AppStore
import time

logger = logging.getLogger(__name__)


class AppStoreScraper:
    """Integration with Apple App Store scraper."""
    
    DEFAULT_LANG = "es"
    RATE_LIMIT_DELAY = 2  # seconds
    
    def __init__(self):
        """Initialize App Store scraper."""
        pass
    
    def fetch_app_data(self, app_id: str, country: str = "us") -> Dict[str, Any]:
        """
        Fetch app metadata from Apple App Store.
        
        Args:
            app_id: App Store app ID (numeric or bundle ID like 'com.example.app')
            country: Country code for localization (default: 'us')
            
        Returns:
            Dictionary containing app metadata
            
        Raises:
            ValueError: If app is not found or invalid app_id
        """
        if not app_id:
            raise ValueError("App ID cannot be empty")
        
        try:
            logger.info(f"Fetching app data from App Store: {app_id} (country: {country})")
            
            # Create AppStore instance and fetch app details
            app_store = AppStore(country=country.lower(), app_name=app_id)
            app_store.review(how_many=1)  # Fetch minimal reviews to get app metadata
            
            if not app_store.reviews:
                # Try alternative: search by app name if bundle ID didn't work
                logger.warning(f"No data found for {app_id}, app may not exist")
                raise ValueError(f"App '{app_id}' not found on App Store")
            
            # Extract app metadata from the scraper
            # Note: app-store-scraper provides limited metadata, mainly focused on reviews
            app_data = {
                'app_name': app_store.app_name or app_id,
                'app_id': app_id,
                'country': country,
            }
            
            logger.debug(f"Successfully fetched app data for {app_id}")
            return app_data
            
        except Exception as e:
            logger.error(f"Failed to fetch app data for {app_id}: {str(e)}")
            raise ValueError(f"App '{app_id}' not found on App Store: {str(e)}")
    
    def fetch_recent_reviews(
        self,
        app_id: str,
        country: str = "us",
        days: int = 7
    ) -> List[Dict[str, Any]]:
        """
        Fetch reviews from the last N days from App Store.
        
        Args:
            app_id: App Store app ID or app name
            country: Country code for localization
            days: Number of days to look back for reviews
            
        Returns:
            List of review dictionaries with keys: at, content, score, source
            
        Raises:
            ValueError: If scraping fails
        """
        logger.info(f"Fetching reviews for {app_id} from last {days} days (country: {country})")
        
        try:
            # Create AppStore instance
            app_store = AppStore(country=country.lower(), app_name=app_id)
            
            # Fetch reviews (app-store-scraper fetches recent reviews)
            # Note: This library doesn't support date filtering directly
            # We'll fetch a reasonable amount and filter by date
            app_store.review(how_many=100)  # Fetch up to 100 recent reviews
            
            if not app_store.reviews:
                logger.info(f"No reviews found for {app_id}")
                return []
            
            # Filter reviews by date
            date_limit = datetime.now() - timedelta(days=days)
            formatted_reviews = []
            
            for review in app_store.reviews:
                try:
                    # Parse review date
                    review_date = review.get('date')
                    if isinstance(review_date, str):
                        review_date = datetime.strptime(review_date, '%Y-%m-%d %H:%M:%S')
                    elif not isinstance(review_date, datetime):
                        continue
                    
                    # Check if review is within date range
                    if review_date >= date_limit:
                        formatted_reviews.append({
                            'at': review_date.date(),
                            'content': review.get('review', ''),
                            'score': int(review.get('rating', 0)),
                            'source': 'iOS'
                        })
                except Exception as e:
                    logger.warning(f"Error parsing review: {e}")
                    continue
            
            logger.info(f"Fetched {len(formatted_reviews)} reviews for {app_id} from last {days} days")
            return formatted_reviews
            
        except Exception as e:
            logger.error(f"Error fetching reviews for {app_id}: {str(e)}")
            raise ValueError(f"Failed to fetch reviews for app '{app_id}': {str(e)}")
    
    def extract_app_info(self, app_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract relevant app information for database storage.
        
        Args:
            app_data: Raw app data from app-store-scraper
            
        Returns:
            Dictionary with standardized app information
            
        Note:
            app-store-scraper provides limited metadata compared to google-play-scraper.
            Some fields will use default values.
        """
        return {
            'app_name': app_data.get('app_name', 'Unknown App'),
            'app_desarrollador': app_data.get('developer', 'Unknown Developer'),
            'app_categoria': app_data.get('category', 'Unknown Category'),
            'app_icon_url': app_data.get('icon', ''),
            'app_descargas': 0,  # App Store doesn't provide download counts
            'total_ratings': app_data.get('ratings_count', 0),
            'rating_average': round(app_data.get('rating', 0.0), 2) if app_data.get('rating') else None,
        }


# Singleton instance
app_store_scraper = AppStoreScraper()
