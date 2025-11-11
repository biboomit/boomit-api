from pydantic import BaseModel, Field
from typing import List, Optional


class InsightItem(BaseModel):
    """Individual insight item"""
    
    type: str = Field(..., description="Type of insight: 'positive' or 'negative'")
    title: str = Field(..., description="Title/summary of the insight")
    change: str = Field(..., description="Change percentage or indicator (e.g., '+23%')")
    summary: str = Field(..., description="Detailed summary of the insight")
    period: str = Field(..., description="Time period for the insight (e.g., '2024-08')")


class AppInsightsResponse(BaseModel):
    """Response model for app insights endpoint"""
    
    insights: List[InsightItem] = Field(
        ..., 
        description="Array of insights derived from app review analysis"
    )

    class Config:
        json_encoders = {}
        schema_extra = {
            "example": {
                "insights": [
                    {
                        "type": "positive",
                        "title": "Diseño moderno bien recibido",
                        "change": "+23%",
                        "summary": "Los usuarios valoran el nuevo diseño y navegación.",
                        "period": "2024-08"
                    },
                    {
                        "type": "negative", 
                        "title": "Aumento de quejas sobre precios",
                        "change": "+45%",
                        "summary": "Usuarios expresan frustración con el nuevo modelo freemium.",
                        "period": "2024-08"
                    }
                ]
            }
        }