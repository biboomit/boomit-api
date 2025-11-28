from enum import Enum
from typing import List
from pydantic import BaseModel, Field


class SentimentType(str, Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    MIXED = "mixed"


class SeverityLevel(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class RecommendationCategory(str, Enum):
    TECHNICAL = "technical"
    UX_DESIGN = "ux_design"
    FEATURE = "feature"
    CONTENT = "content"
    PERFORMANCE = "performance"


class PriorityLevel(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class InsightType(str, Enum):
    USER_SEGMENT = "user_segment"
    FEATURE_GAP = "feature_gap"
    COMPETITIVE = "competitive"
    ADOPTION_BARRIER = "adoption_barrier"
    SATISFACTION_DRIVER = "satisfaction_driver"
    CHURN_RISK = "churn_risk"


class ReviewLength(str, Enum):
    VERY_SHORT = "very_short"
    SHORT = "short"
    MEDIUM = "medium"
    LONG = "long"
    VERY_LONG = "very_long"


class ConfidenceLevel(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class SentimentSummary(BaseModel):
    overall: SentimentType
    score: int = Field(..., ge=1, le=5)
    description: str


class TechnicalIssue(BaseModel):
    issue: str
    severity: SeverityLevel
    context: str


class Strength(BaseModel):
    feature: str
    userImpact: str


class Weakness(BaseModel):
    aspect: str
    userImpact: str


class Recommendation(BaseModel):
    category: RecommendationCategory
    priority: PriorityLevel
    action: str
    expectedImpact: str


class Insight(BaseModel):
    observation: str
    type: InsightType
    strategicValue: str


class Metadata(BaseModel):
    reviewLength: ReviewLength
    analysisConfidence: ConfidenceLevel
    languageDetected: str


class ReviewAnalysis(BaseModel):
    reviewDate: str
    sentimentSummary: SentimentSummary
    technicalIssues: List[TechnicalIssue]
    strengths: List[Strength]
    weaknesses: List[Weakness]
    recommendations: List[Recommendation]
    insights: List[Insight]
    metadata: Metadata