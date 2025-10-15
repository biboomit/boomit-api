from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class ReviewResponse(BaseModel):
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


class Review(BaseModel):
    review_id: str = Field(..., description="Unique identifier for the review history")
    rating: int = Field(..., ge=1, le=5, description="Rating score between 1 and 5")
    comment: str = Field(..., description="Comment content of the review")
    date: datetime = Field(..., description="Date when the review was made")


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
