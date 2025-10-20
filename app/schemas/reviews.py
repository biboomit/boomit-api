from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import datetime


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
                    "five_star_reviews": 150,
                    "four_star_reviews": 50,
                    "three_star_reviews": 30,
                    "two_star_reviews": 15,
                    "one_star_reviews": 5,
                },
                "time_frame": {
                    "date_from": "2023-01-01T00:00:00Z",
                    "date_to": "2023-10-15T23:59:59Z",
                },
            }
        }