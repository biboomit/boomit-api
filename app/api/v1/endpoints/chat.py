"""
Chat endpoints with SSE streaming support.

Provides REST API for chat sessions:
- POST /sessions: Create new chat session
- POST /sessions/{session_id}/messages: Send message with SSE streaming
- GET /sessions/{session_id}/messages: Get conversation history
"""

import logging
from typing import AsyncGenerator
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sse_starlette.sse import EventSourceResponse

from app.schemas.chat import (
    CreateSessionRequest,
    CreateSessionResponse,
    SendMessageRequest,
    ChatHistoryResponse,
    ChatMessage
)
from app.middleware.auth import get_current_user
from app.services.chat_context_builder import chat_context_builder
from app.services.chat_service import chat_service
from app.utils.session_manager import session_manager
from app.core.exceptions import (
    ChatSessionNotFoundError,
    ChatSessionExpiredError,
    BoomitAPIException
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


def _extract_user_info(current_user: dict) -> str:
    """
    Extract user_id from JWT payload.
    
    Args:
        current_user: JWT payload from get_current_user
    
    Returns:
        user_id
    
    Raises:
        HTTPException: If required fields are missing
    """
    user_id = current_user.get("sub") or current_user.get("user_id") or current_user.get("userId")
    
    if not user_id:
        raise HTTPException(
            status_code=401,
            detail="Token missing user identifier"
        )
    
    return user_id


@router.post("/sessions", response_model=CreateSessionResponse)
async def create_chat_session(
    request: CreateSessionRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Create a new chat session for an app.
    
    This endpoint:
    1. Validates app ownership
    2. Loads analysis context (sentiment, themes, reviews)
    3. Creates a new session with 30-minute TTL
    
    """
    user_id = _extract_user_info(current_user)
    logger.info(f"🟢 Creando sesión de chat para usuario {user_id}, app {request.app_id}")
    
    try:
        # Check session limit
        user_sessions = session_manager.get_user_sessions(user_id)
        if len(user_sessions) >= 1:
            raise HTTPException(
                status_code=429,
                detail="Maximum active sessions reached (5). Please close an existing session."
            )
        
        # Build context
        context = await chat_context_builder.build_context(
            request.app_id,
            days_back=180
        )
        
        # Create session
        session = session_manager.create_session(
            user_id=user_id,
            app_id=request.app_id,
            context=context
        )
        
        # Calculate expiration
        from datetime import timedelta
        expires_at = session.created_at + timedelta(minutes=30)
        
        return CreateSessionResponse(
            session_id=session.session_id,
            app_id=session.app_id,
            created_at=session.created_at,
            expires_at=expires_at
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating chat session: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to create chat session"
        )


@router.post("/sessions/{session_id}/messages")
async def send_message(
    session_id: str,
    request: SendMessageRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Send a message and receive AI response via Server-Sent Events (SSE).
    
    **Response format:** text/event-stream
    
    The response streams tokens as they arrive:
    ```
    data: {"token": "Los", "done": false}
    
    data: {"token": " principales", "done": false}
    
    data: {"token": " problemas", "done": false}
    
    data: {"token": "", "done": true}
    ```
    """
    user_id = _extract_user_info(current_user)
    
    logger.info(
        f"User {user_id} sending message to session {session_id}: "
        f"{request.message[:50]}..."
    )
    
    try:
        # Get session (validates ownership and expiration)
        session = session_manager.get_session(session_id, user_id)
        
        # Add user message to session
        user_message = ChatMessage(
            role="user",
            content=request.message,
            timestamp=datetime.utcnow()
        )
        session_manager.add_message(session_id, user_message)
        
        # Stream AI response
        async def event_generator() -> AsyncGenerator[str, None]:
            """Generate SSE events from AI stream"""
            try:
                accumulated_response = ""
                
                # Stream tokens from OpenAI
                async for token in chat_service.stream_response(session, request.message):
                    accumulated_response += token
                    
                    # Send token as SSE event
                    yield {
                        "event": "message",
                        "data": {
                            "token": token,
                            "done": False
                        }
                    }
                
                # Add assistant message to session
                assistant_message = ChatMessage(
                    role="assistant",
                    content=accumulated_response,
                    timestamp=datetime.utcnow()
                )
                session_manager.add_message(session_id, assistant_message)
                
                # Send completion event
                yield {
                    "event": "message",
                    "data": {
                        "token": "",
                        "done": True,
                        "full_response": accumulated_response
                    }
                }
                
                logger.info(
                    f"Completed streaming response for session {session_id}. "
                    f"Response length: {len(accumulated_response)} chars"
                )
                
            except Exception as e:
                logger.error(f"Error during streaming: {e}")
                yield {
                    "event": "error",
                    "data": {
                        "error": "Failed to generate response",
                        "detail": str(e)
                    }
                }
        
        return EventSourceResponse(event_generator())
        
    except ChatSessionNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ChatSessionExpiredError as e:
        raise HTTPException(status_code=410, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        # Message limit exceeded
        raise HTTPException(status_code=429, detail=str(e))
    except Exception as e:
        logger.error(f"Error sending message: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to process message"
        )


@router.get("/sessions/{session_id}/messages", response_model=ChatHistoryResponse)
async def get_conversation_history(
    session_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Get conversation history for a session.
    
    Returns all messages in chronological order.
    """
    user_id = _extract_user_info(current_user)
    
    logger.info(f"User {user_id} retrieving history for session {session_id}")
    
    try:
        # Get session (validates ownership and expiration)
        session = session_manager.get_session(session_id, user_id)
        
        return ChatHistoryResponse(
            session_id=session.session_id,
            app_id=session.app_id,
            messages=session.messages,
            created_at=session.created_at,
            last_activity=session.last_activity
        )
        
    except ChatSessionNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ChatSessionExpiredError as e:
        raise HTTPException(status_code=410, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"Error retrieving history: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve conversation history"
        )


@router.get("/sessions/{session_id}/stats")
async def get_session_stats(
    session_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Get session statistics and metadata.
    
    Returns:
    - Message count
    - Session age
    - Context summary
    """
    user_id = _extract_user_info(current_user)
    
    try:
        session = session_manager.get_session(session_id, user_id)
        
        return {
            "session_id": session.session_id,
            "app_id": session.app_id,
            "message_count": len(session.messages),
            "created_at": session.created_at,
            "last_activity": session.last_activity,
            "age_minutes": (datetime.utcnow() - session.created_at).total_seconds() / 60,
            "context_summary": {
                "total_reviews": session.context.get("stats", {}).get("total_reviews", 0),
                "avg_rating": session.context.get("stats", {}).get("avg_rating", 0),
                "themes_count": len(session.context.get("emerging_themes", []))
            }
        }
        
    except ChatSessionNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ChatSessionExpiredError as e:
        raise HTTPException(status_code=410, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"Error retrieving session stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve session stats")


@router.get("/sessions")
async def list_user_sessions(
    current_user: dict = Depends(get_current_user)
):
    """
    List all active sessions for the current user.
    
    Returns sessions sorted by last activity (most recent first).
    """
    user_id = _extract_user_info(current_user)
    
    try:
        sessions = session_manager.get_user_sessions(user_id)
        
        return {
            "total": len(sessions),
            "sessions": [
                {
                    "session_id": s.session_id,
                    "app_id": s.app_id,
                    "message_count": len(s.messages),
                    "created_at": s.created_at,
                    "last_activity": s.last_activity
                }
                for s in sessions
            ]
        }
        
    except Exception as e:
        logger.error(f"Error listing sessions: {e}")
        raise HTTPException(status_code=500, detail="Failed to list sessions")


@router.get("/health")
async def chat_health_check():
    """
    Health check endpoint for chat service.
    
    Returns session manager statistics.
    """
    try:
        stats = session_manager.get_stats()
        return {
            "status": "healthy",
            "service": "chat",
            "stats": stats
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "unhealthy",
            "service": "chat",
            "error": str(e)
        }
