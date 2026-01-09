from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from datetime import date


class AppDetailsResponse(BaseModel):
    """Response model for app details from DIM_MAESTRO_REVIEWS"""

    app_id: str = Field(..., alias="appId", description="Unique app identifier")
    app_name: str = Field(..., alias="appName", description="Application name")
    store: str = Field(..., description="Operating system (android/ios)")
    developer: str = Field(..., description="Developer name")
    rating_average: Optional[float] = Field(
        None,
        alias="ratingAverage",
        ge=0.0,
        le=5.0,
        description="Average rating score from reviews"
    )
    total_ratings: Optional[int] = Field(
        None,
        alias="totalRatings",
        ge=0,
        description="Total number of ratings from reviews"
    )
    downloads: int = Field(0, ge=0, description="Number of downloads")
    last_update: date = Field(..., alias="lastUpdate", description="Last update date")
    icon_url: str = Field("", alias="iconUrl", description="App icon URL")
    category: str = Field("Unknown", description="App category")

    @field_validator("store")
    @classmethod
    def normalize_store(cls, v: str) -> str:
        """Normalize store to lowercase"""
        return v.lower() if v else v

    @field_validator("app_name", "developer", "category")
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        """Strip whitespace from string fields"""
        return v.strip() if v else v

    class Config:
        populate_by_name = True
        json_encoders = {
            date: lambda v: v.strftime("%Y-%m-%d")
        }
        schema_extra = {
            "example": {
                "appId": "com.farmatodo.app",
                "appName": "Farmatodo",
                "store": "android",
                "developer": "Farmatodo Inc.",
                "ratingAverage": 4.2,
                "totalRatings": 12543,
                "downloads": 2100000,
                "lastUpdate": "2024-08-10",
                "iconUrl": "https://play-lh.googleusercontent.com/...",
                "category": "Health & Fitness"
            }
        }

        
class AppSearchResponse(BaseModel):
    """Response model for app search endpoint containing array of apps"""
    
    apps: List[AppDetailsResponse] = Field(
        ..., 
        description="Array of apps matching search criteria"
    )
    
    class Config:
        schema_extra = {
            "example": {
                "apps": [
                    {
                        "appId": "com.farmatodo.app",
                        "appName": "Farmatodo",
                        "store": "android",
                        "developer": "Farmatodo Inc.",
                        "ratingAverage": 4.2,
                        "totalRatings": 12543,
                        "downloads": 2100000,
                        "lastUpdate": "2024-08-10",
                        "iconUrl": "https://play-lh.googleusercontent.com/...",
                        "category": "Health & Fitness"
                    }
                ]
            }
        }