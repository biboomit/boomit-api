"""Google Play Store scraper integration using google-play-scraper library."""

import logging
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timedelta
import time
from google_play_scraper import app as gps_app, reviews, Sort
import pandas as pd

logger = logging.getLogger(__name__)


class GooglePlayScraper:
    """Integration with Google Play Store scraper."""
    
    DEFAULT_LANG = "es"
    MAX_ITERATIONS = 10
    REVIEWS_PER_BATCH = 200
    RATE_LIMIT_DELAY = 2  # seconds
    
    def __init__(self):
        """Initialize Google Play scraper."""
        pass
    
    def fetch_app_data(self, app_id: str, country: str = "us") -> Dict[str, Any]:
        """
        Fetch app metadata from Google Play Store.
        
        Args:
            app_id: Google Play Store app ID (e.g., 'com.example.app')
            country: Country code for localization (default: 'us')
            
        Returns:
            Dictionary containing app metadata
            
        Raises:
            ValueError: If app is not found or invalid app_id
        """
        if not app_id:
            raise ValueError("App ID cannot be empty")
        
        try:
            logger.info(f"Fetching app data from Play Store: {app_id} (country: {country})")
            app_data = gps_app(app_id, lang=self.DEFAULT_LANG, country=country.lower())
            
            logger.debug(f"Successfully fetched app data for {app_id}")
            return app_data
            
        except Exception as e:
            logger.error(f"Failed to fetch app data for {app_id}: {str(e)}")
            raise ValueError(f"App '{app_id}' not found on Google Play Store: {str(e)}")
    
    def fetch_recent_reviews(
        self,
        app_id: str,
        country: str = "us",
        days: int = 7
    ) -> List[Dict[str, Any]]:
        """
        Fetch reviews from the last N days from Google Play Store.
        
        Args:
            app_id: Google Play Store app ID
            country: Country code for localization
            days: Number of days to look back for reviews
            
        Returns:
            List of review dictionaries with keys: at, content, score, source
            
        Raises:
            ValueError: If scraping fails
        """
        all_reviews = []
        continuation_token = None
        date_limit = datetime.today() - timedelta(days=days)
        
        logger.info(f"Fetching reviews for {app_id} from last {days} days (country: {country})")
        
        try:
            for iteration in range(self.MAX_ITERATIONS):
                result, continuation_token = reviews(
                    app_id,
                    lang=self.DEFAULT_LANG,
                    country=country.lower(),
                    count=self.REVIEWS_PER_BATCH,
                    sort=Sort.NEWEST,
                    continuation_token=continuation_token,
                )
                
                # Filter reviews by date
                for review in result:
                    review_date = pd.to_datetime(review["at"])
                    if review_date >= date_limit:
                        all_reviews.append(review)
                    else:
                        # Stop if we've reached reviews older than date_limit
                        continuation_token = None
                        break
                
                if not continuation_token:
                    break
                
                # Rate limiting
                time.sleep(self.RATE_LIMIT_DELAY)
                
            logger.info(f"Fetched {len(all_reviews)} reviews for {app_id}")
            
            # Format reviews
            formatted_reviews = []
            for review in all_reviews:
                formatted_reviews.append({
                    'at': pd.to_datetime(review['at']).date(),
                    'content': review['content'],
                    'score': review['score'],
                    'source': 'Android'
                })
            
            return formatted_reviews
            
        except Exception as e:
            logger.error(f"Error fetching reviews for {app_id}: {str(e)}")
            raise ValueError(f"Failed to fetch reviews for app '{app_id}': {str(e)}")
    
    def parse_installs(self, installs_str: Optional[str]) -> int:
        """
        Parse Google Play Store installs string to numeric value.
        
        Args:
            installs_str: Formatted installs (e.g., "1,000,000+" or "50.000+")
            
        Returns:
            Numeric value for database storage
            
        Examples:
            "1,000+" → 1000
            "5,000,000+" → 5000000
            "50.000+" → 50000 (European format)
        """
        if not installs_str or installs_str in ["N/A", "", "Not available", "0"]:
            return 0
        
        # Convert to string and remove plus sign
        clean_str = str(installs_str).replace("+", "").strip()
        
        try:
            # Handle different number formats
            if "," in clean_str:
                # US format with commas (1,000,000)
                clean_str = clean_str.replace(",", "")
                return int(clean_str)
            elif "." in clean_str:
                # Could be European thousands (1.000.000) or decimal (50.0)
                parts = clean_str.split(".")
                if len(parts) == 2:
                    # Single dot - check if it's decimal or thousands
                    if len(parts[1]) <= 2:
                        # Likely decimal (50.0)
                        return int(float(clean_str))
                    else:
                        # Likely thousands separator (50.000)
                        clean_str = clean_str.replace(".", "")
                        return int(clean_str)
                else:
                    # Multiple dots - European thousands format (1.000.000)
                    clean_str = clean_str.replace(".", "")
                    return int(clean_str)
            else:
                # No separators, plain number
                return int(clean_str)
                
        except (ValueError, TypeError) as e:
            logger.warning(f"Could not parse installs string: {installs_str} - {str(e)}")
            return 0
    
    def extract_app_info(self, app_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract relevant app information for database storage.
        
        Args:
            app_data: Raw app data from google-play-scraper
            
        Returns:
            Dictionary with standardized app information
        """
        return {
            'app_name': app_data.get('title', 'Unknown App'),
            'app_desarrollador': app_data.get('developer', 'Unknown Developer'),
            'app_categoria': app_data.get('genre', 'Unknown Category'),
            'app_icon_url': app_data.get('icon', ''),
            'app_descargas': self.parse_installs(app_data.get('installs', '0')),
            'total_ratings': app_data.get('ratings', 0),
            'rating_average': round(app_data.get('score', 0.0), 2) if app_data.get('score') else None,
        }


# Singleton instance
google_play_scraper = GooglePlayScraper()
