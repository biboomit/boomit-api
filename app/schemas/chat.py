"""
Pydantic schemas for chat functionality.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict


class ChatMessage(BaseModel):
    """Single message in a chat conversation"""
    
    role: str = Field(..., description="Message role: 'user' or 'assistant'")
    content: str = Field(..., description="Message content")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Message timestamp")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "role": "user",
                "content": "¿Cuáles son los principales problemas reportados?",
                "timestamp": "2025-12-08T10:30:00Z"
            }
        }
    )


class CreateSessionRequest(BaseModel):
    """Request to create a new chat session"""
    
    app_id: str = Field(..., description="App ID to chat about")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "app_id": "com.lulubit"
            }
        }
    )


class CreateSessionResponse(BaseModel):
    """Response after creating a chat session"""
    
    session_id: str = Field(..., description="Unique session identifier")
    app_id: str = Field(..., description="App ID associated with this session")
    created_at: datetime = Field(..., description="Session creation timestamp")
    expires_at: datetime = Field(..., description="Session expiration timestamp")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "session_id": "session_abc123xyz",
                "app_id": "com.lulubit",
                "created_at": "2025-12-08T10:00:00Z",
                "expires_at": "2025-12-08T10:30:00Z"
            }
        }
    )


class SendMessageRequest(BaseModel):
    """Request to send a message in a chat session"""
    
    message: str = Field(..., min_length=1, max_length=1000, description="User message")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "message": "¿Cuáles son los principales problemas reportados en las últimas reviews?"
            }
        }
    )


class ChatHistoryResponse(BaseModel):
    """Response with chat conversation history"""
    
    session_id: str = Field(..., description="Session identifier")
    app_id: str = Field(..., description="App ID")
    messages: List[ChatMessage] = Field(..., description="Conversation messages")
    created_at: datetime = Field(..., description="Session creation timestamp")
    last_activity: datetime = Field(..., description="Last activity timestamp")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "session_id": "session_abc123xyz",
                "app_id": "com.lulubit",
                "messages": [
                    {
                        "role": "user",
                        "content": "¿Cuáles son los principales problemas?",
                        "timestamp": "2025-12-08T10:00:00Z"
                    },
                    {
                        "role": "assistant",
                        "content": "Los principales problemas reportados son...",
                        "timestamp": "2025-12-08T10:00:05Z"
                    }
                ],
                "created_at": "2025-12-08T10:00:00Z",
                "last_activity": "2025-12-08T10:00:05Z"
            }
        }
    )


class ChatSession(BaseModel):
    """Internal model for chat session storage"""
    
    session_id: str
    user_id: str
    company_id: str
    app_id: str
    context: Dict[str, Any]  # Loaded analysis context
    messages: List[ChatMessage] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_activity: datetime = Field(default_factory=datetime.utcnow)
    
    model_config = ConfigDict(arbitrary_types_allowed=True)
