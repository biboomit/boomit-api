"""
Marketing Chat Schemas

Pydantic models for marketing report chat sessions.
Reuses generic models from chat.py where applicable.
"""

from datetime import datetime
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

# Import reusable generic models from chat schemas
from app.schemas.chat import ChatMessage, SendMessageRequest


class CreateMarketingChatSessionRequest(BaseModel):
    """
    Request to create a new marketing chat session.
    
    The session will load context from a specific marketing report.
    """
    report_id: str = Field(
        ...,
        description="ID of the marketing report to chat about",
        min_length=1,
        max_length=100
    )


class CreateMarketingChatSessionResponse(BaseModel):
    """Response after creating a marketing chat session"""
    session_id: str = Field(..., description="Unique session identifier")
    report_id: str = Field(..., description="Associated marketing report ID")
    agent_config_id: str = Field(..., description="Agent configuration ID")
    report_period: Optional[str] = Field(None, description="Report period (e.g., '2026-01-01 to 2026-01-21')")
    created_at: datetime = Field(..., description="Session creation timestamp")
    expires_at: datetime = Field(..., description="Session expiration timestamp")


class MarketingChatSession(BaseModel):
    """
    Marketing chat session model.
    
    Stores session state including report context and conversation history.
    """
    session_id: str
    user_id: str
    report_id: str
    agent_config_id: str
    context: Dict[str, Any] = Field(
        default_factory=dict,
        description="Loaded report context including report_json, agent_config, data_window"
    )
    messages: List[ChatMessage] = Field(
        default_factory=list,
        description="Conversation history"
    )
    created_at: datetime
    last_activity: datetime


class MarketingChatHistoryResponse(BaseModel):
    """Response containing marketing chat conversation history"""
    session_id: str
    report_id: str
    agent_config_id: str
    messages: List[ChatMessage]
    created_at: datetime
    last_activity: datetime
