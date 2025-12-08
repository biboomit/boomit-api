from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict
from typing import Optional, Any
from datetime import datetime, date


class ReviewSourceResponse(BaseModel):
    """Response model for review source with aggregated metadata"""

    app_id: str = Field(..., description="App ID associated with the reviews")
    source: str = Field(..., description="Source of the reviews (Android/iOS)")
    total_reviews: int = Field(
        ..., ge=0, description="Total number of reviews for this app"
    )
    average_rating: float = Field(
        ..., ge=0.0, le=5.0, description="Average rating across all reviews"
    )
    first_review_date: datetime = Field(..., description="Date of the first review")
    last_review_date: datetime = Field(
        ..., description="Date of the most recent review"
    )

    @field_validator("source")
    @classmethod
    def normalize_source(cls, v: str) -> str:
        """Normalize source to lowercase"""
        return v.lower() if v else v

    class Config:
        from_attributes = True
        orm_mode = True
        schema_extra = {
            "example": {
                "app_id": "com.example.app",
                "source": "android",
                "total_reviews": 250,
                "average_rating": 4.2,
                "first_review_date": "2023-01-01T08:00:00Z",
                "last_review_date": "2023-10-15T10:30:00Z",
            }
        }


class ReviewSourceListResponse(BaseModel):
    """Paginated list of review sources"""

    sources: list[ReviewSourceResponse] = Field(
        ..., description="List of review sources with metadata"
    )
    total: int = Field(..., ge=0, description="Total number of sources")
    page: int = Field(..., ge=1, description="Current page number")
    per_page: int = Field(..., ge=1, description="Number of items per page")

    class Config:
        schema_extra = {
            "example": {
                "sources": [
                    {
                        "app_id": "com.example.app",
                        "source": "android",
                        "total_reviews": 250,
                        "average_rating": 4.2,
                        "first_review_date": "2023-01-01T08:00:00Z",
                        "last_review_date": "2023-10-15T10:30:00Z",
                    }
                ],
                "total": 5,
                "page": 1,
                "per_page": 10,
            }
        }


class Review(BaseModel):
    """Individual review model"""

    review_id: str = Field(..., description="Unique identifier for the review history")
    rating: int = Field(..., ge=1, le=5, description="Rating score between 1 and 5")
    comment: str = Field(..., description="Comment content of the review")
    date: datetime = Field(..., description="Date when the review was made")

    class Config:
        schema_extra = {
            "example": {
                "review_id": "rev123",
                "rating": 5,
                "comment": "Great app!",
                "date": "2023-10-01T12:34:56Z",
            }
        }


class PaginatedReviewsResponse(BaseModel):
    """Paginated list of reviews for a specific app"""

    app_id: str = Field(..., description="App ID associated with the reviews")
    source: str = Field(..., description="Source of the reviews (Android/iOS)")
    reviews: list[Review] = Field(..., description="List of reviews")
    total: int = Field(..., ge=0, description="Total number of reviews for this app")
    page: int = Field(..., ge=1, description="Current page number")
    per_page: int = Field(..., ge=1, description="Number of items per page")

    @field_validator("source")
    @classmethod
    def normalize_source(cls, v: str) -> str:
        """Normalize source to lowercase"""
        return v.lower() if v else v

    class Config:
        from_attributes = True
        orm_mode = True
        schema_extra = {
            "example": {
                "app_id": "com.example.app",
                "source": "android",
                "reviews": [
                    {
                        "review_id": "rev123",
                        "rating": 5,
                        "comment": "Great app!",
                        "date": "2023-10-01T12:34:56Z",
                    },
                    {
                        "review_id": "rev124",
                        "rating": 4,
                        "comment": "Good but needs improvement.",
                        "date": "2023-10-02T14:20:00Z",
                    },
                ],
                "total": 250,
                "page": 1,
                "per_page": 20,
            }
        }


class ReviewResponse(BaseModel):
    """Legacy response model - DEPRECATED: Use PaginatedReviewsResponse instead"""

    app_id: str = Field(..., description="App ID associated with the review")
    source: str = Field(..., description="Source of the review")
    reviews: list["Review"] = Field(..., description="List of reviews")

    class Config:
        from_attributes = True
        orm_mode = True
        schema_extra = {
            "example": {
                "app_id": "com.example.app",
                "source": "Google Play",
                "reviews": [
                    {
                        "review_id": "rev123",
                        "rating": 5,
                        "comment": "Great app!",
                        "date": "2023-10-01T12:34:56",
                    },
                    {
                        "review_id": "rev124",
                        "rating": 4,
                        "comment": "Good but needs improvement.",
                        "date": "2023-10-02T14:20:00",
                    },
                ],
            }
        }


class ReviewListResponse(BaseModel):
    reviews: list[ReviewResponse]
    total: int
    page: int
    per_page: int


class ReviewInternal(BaseModel):
    review_historico_id: str
    app_id: str
    fecha: datetime
    content: str
    score: int
    source: str
    created_at: datetime
    updated_at: Optional[datetime]

    def to_dict(self):
        return {
            "review_historico_id": self.review_historico_id,
            "app_id": self.app_id,
            "fecha": self.fecha,
            "content": self.content,
            "score": self.score,
            "source": self.source,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class MetricsResponse(BaseModel):
    """Response model for app metrics"""

    app_id: str = Field(..., description="App ID associated with the metrics")
    source: str = Field(..., description="Source of the reviews (Android/iOS)")
    metrics: dict = Field(..., description="Metrics data for the specified app")
    time_frame: dict = Field(..., description="Time frame for the metrics")

    class Config:
        schema_extra = {
            "example": {
                "app_id": "com.example.app",
                "source": "android",
                "metrics": {
                    "total_reviews": 250,
                    "average_rating": 4.2,
                    "reviews_by_score": {5: 150, 4: 50, 3: 30, 2: 15, 1: 5},
                },
                "time_frame": {
                    "date_from": "2023-01-01T00:00:00Z",
                    "date_to": "2023-10-15T23:59:59Z",
                },
            }
        }


class AnalysisParameters(BaseModel):
    """Parameters for AI analysis"""

    from_date: Optional[date] = Field(None, description="Start date for analysis")
    to_date: Optional[date] = Field(None, description="End date for analysis")
    response_language: Optional[str] = Field(
        "en", description="Language for the response"
    )
    min_rating: Optional[int] = Field(
        None, ge=1, le=5, description="Minimum rating filter"
    )
    max_rating: Optional[int] = Field(
        None, ge=1, le=5, description="Maximum rating filter"
    )

    @field_validator("response_language")
    @classmethod
    def normalize_language(cls, v: Optional[str]) -> Optional[str]:
        """Normalize response language to lowercase"""
        return v.lower() if v else v

    @field_validator("min_rating", "max_rating")
    @classmethod
    def validate_ratings(cls, v: Optional[int]) -> Optional[int]:
        """Ensure ratings are within valid range"""
        if v is not None and (v < 1 or v > 5):
            raise ValueError("Ratings must be between 1 and 5")
        return v

    @field_validator("to_date")
    @classmethod
    def validate_date_range(cls, v: Optional[datetime], info) -> Optional[datetime]:
        """Validate that to_date is not earlier than from_date"""
        from_date = info.data.get("from_date")
        if v is not None and from_date is not None and v < from_date:
            raise ValueError("to_date cannot be earlier than from_date")
        return v
    
    @model_validator(mode='after')
    def validate_rating_range(self) -> 'AnalysisParameters':
        """Ensure min_rating is not greater than max_rating"""
        if (self.min_rating is not None and 
            self.max_rating is not None and 
            self.min_rating > self.max_rating):
            raise ValueError("min_rating cannot be greater than max_rating")
        return self

    class Config:
        schema_extra = {
            "example": {
                "from_date": "2024-01-01",
                "to_date": "2024-12-31",
                "response_language": "en",
                "min_rating": 1,
                "max_rating": 5,
            }
        }


class AIAnalysisRequest(BaseModel):
    """Request model for AI analysis of reviews"""

    app_id: str = Field(..., description="App ID associated with the reviews")
    analysis_type: str = Field(..., description="Type of AI analysis to perform")
    parameters: Optional[AnalysisParameters] = Field(
        None, description="Additional parameters for the AI analysis"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "app_id": "com.example.app",
                "analysis_type": "sentiment",
                "parameters": {
                    "from_date": "2024-01-01",
                    "to_date": "2024-12-31",
                    "response_language": "es",
                    "min_rating": 3,
                    "max_rating": 5,
                },
            }
        }


class AIAnalysisResponse(BaseModel):
    """Response model for AI analysis request"""
    batch: Any = Field(..., description="Batch information from OpenAI")
    file_uploaded: Any = Field(..., description="File upload information from OpenAI")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "batch": {
                    "id": "batch_123",
                    "status": "processing"
                },
                "file_uploaded": {
                    "id": "file_123",
                    "filename": "reviews.jsonl"
                }
            }
        }
    )
