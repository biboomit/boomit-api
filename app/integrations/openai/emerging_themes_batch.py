import io
import json
from datetime import datetime
from typing import List, Tuple
from openai import OpenAI

from app.core.config import OpenAIConfig
from app.integrations.openai.emerging_themes_prompt import EMERGING_THEMES_PROMPT


class OpenAIEmergingThemesBatchIntegration:
    """
    Integration class for analyzing emerging themes from reviews using OpenAI Batch API.
    
    This class sends ALL reviews in a SINGLE batch request to identify patterns and 
    recurring themes across the entire dataset, unlike the individual review analysis
    done by OpenAIBatchIntegration.
    """

    def __init__(self):
        self.api_key = OpenAIConfig().get_api_key()
        self.client = OpenAI(api_key=self.api_key)

    def analyze_emerging_themes(
        self,
        app_id: str,
        app_name: str,
        app_category: str,
        reviews: List[Tuple[str, int, datetime]],  # (content, score, date)
        start_date: datetime,
        end_date: datetime,
    ) -> Tuple[any, any]:
        """
        Analyze reviews to identify emerging themes.

        Args:
            app_id: Application ID
            app_name: Application name
            app_category: Application category
            reviews: List of tuples containing (content, score, date)
            start_date: Start date of the analysis period
            end_date: End date of the analysis period

        Returns:
            Tuple of (uploaded_file, batch) from OpenAI API
        """
        # Create the JSONL file with a single request containing all reviews
        jsonl_content = self._create_emerging_themes_jsonl(
            app_id=app_id,
            app_name=app_name,
            app_category=app_category,
            reviews=reviews,
            start_date=start_date,
            end_date=end_date,
        )

        # Upload and create batch
        return self._upload_and_create_batch(jsonl_content, app_id)

    def _create_emerging_themes_jsonl(
        self,
        app_id: str,
        app_name: str,
        app_category: str,
        reviews: List[Tuple[str, int, datetime]],
        start_date: datetime,
        end_date: datetime,
    ) -> str:
        """
        Create a JSONL file with a SINGLE request containing ALL reviews.

        The prompt is constructed by replacing placeholders and including all reviews
        as context for the analysis.
        """
        total_reviews = len(reviews)

        # Build the system prompt with replaced placeholders
        system_prompt = self._build_system_prompt(
            app_id=app_id,
            app_name=app_name,
            app_category=app_category,
            total_reviews=total_reviews,
            start_date=start_date,
            end_date=end_date,
        )

        # Build the user content with all reviews
        user_content = self._build_user_content(reviews)

        # Create the request body
        body = {
            "model": OpenAIConfig().get_model(),
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.7,
            "max_tokens": 4000,
            "metadata": {
                "analysis_period_start": start_date.strftime("%Y-%m-%d"),
                "analysis_period_end": end_date.strftime("%Y-%m-%d"),
                "total_reviews_analyzed": total_reviews,
                "app_id": app_id,
                "app_name": app_name,
                "app_category": app_category,
            },
        }

        # Create the batch request line with a unique custom_id
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        request_line = {
            "custom_id": f"emerging-themes-{app_id}-{timestamp}",
            "method": "POST",
            "url": "/v1/chat/completions",
            "body": body,
        }

        # Return as JSONL (single line)
        return json.dumps(request_line)

    def _build_system_prompt(
        self,
        app_id: str,
        app_name: str,
        app_category: str,
        total_reviews: int,
        start_date: datetime,
        end_date: datetime,
    ) -> str:
        """Build the system prompt with all placeholders replaced."""
        
        # Replace placeholders in the prompt template
        return EMERGING_THEMES_PROMPT.format(
            app_id=app_id,
            app_name=app_name,
            app_category=app_category,
            total_reviews=total_reviews,
            start_date=start_date.strftime("%Y-%m-%d"),
            end_date=end_date.strftime("%Y-%m-%d"),
        )

    def _build_user_content(self, reviews: List[Tuple[str, int, datetime]]) -> str:
        """
        Build user content with all reviews formatted.

        Format: Each review as "Date | Score: X/5 | Content"
        """
        formatted_reviews = []

        for idx, (content, score, review_date) in enumerate(reviews, 1):
            date_str = review_date.strftime("%Y-%m-%d")
            formatted_review = f"Review {idx} | {date_str} | Score: {score}/5\n{content}\n"
            formatted_reviews.append(formatted_review)

        # Join all reviews with separator
        all_reviews = "\n" + "="*80 + "\n\n".join(formatted_reviews)

        return f"""A continuación se presentan {len(reviews)} reviews de usuarios para analizar: 
        
        {all_reviews}
        
        Analiza estas reviews e identifica los temas emergentes según las instrucciones proporcionadas en el prompt del sistema."""

    def _upload_and_create_batch(self, jsonl_content: str, app_id: str):
        """
        Upload the JSONL file and create a batch job.

        Args:
            jsonl_content: JSONL formatted string
            app_id: Application ID for metadata

        Returns:
            Tuple of (uploaded_file, batch)
        """
        # Upload file
        uploaded_file = self.client.files.create(
            file=io.BytesIO(jsonl_content.encode("utf-8")),
            purpose="batch",
        )

        # Create batch
        batch = self.client.batches.create(
            input_file_id=uploaded_file.id,
            endpoint="/v1/chat/completions",
            completion_window="24h",
            metadata={
                "job": "emerging_themes_analysis",
                "app_id": app_id,
                "analysis_type": "reviews_pattern_detection",
            },
        )

        return uploaded_file, batch
