"""
Marketing Chat endpoints with SSE streaming support.

Provides REST API for marketing report chat sessions:
- POST /marketing-chat/sessions: Create new chat session for a report
- POST /marketing-chat/sessions/{session_id}/messages: Send message with SSE streaming
- GET /marketing-chat/sessions/{session_id}/messages: Get conversation history
- GET /marketing-chat/sessions/{session_id}/stats: Get session statistics
- GET /marketing-chat/sessions: List user's active sessions
- GET /marketing-chat/health: Health check
"""

import logging
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sse_starlette.sse import EventSourceResponse

from app.schemas.marketing_chat import (
    CreateMarketingChatSessionRequest,
    CreateMarketingChatSessionResponse,
    MarketingChatHistoryResponse,
    MarketingChatSession
)
from app.schemas.chat import SendMessageRequest, ChatMessage
from app.middleware.auth import get_current_user
from app.services.marketing_context_builder import marketing_context_builder
from app.services.marketing_chat_service import marketing_chat_service
from app.utils.session_manager import session_manager
from app.core.config import settings
from app.core.exceptions import (
    ChatSessionNotFoundError,
    ChatSessionExpiredError,
    BoomitAPIException
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/marketing-chat", tags=["marketing-chat"])


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


@router.post("/sessions", response_model=CreateMarketingChatSessionResponse)
async def create_marketing_chat_session(
    request: CreateMarketingChatSessionRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Create a new marketing chat session for a report.
    
    This endpoint:
    1. Validates report ownership
    2. Loads report context (report JSON, agent config, data window)
    3. Creates a new session with 30-minute TTL
    """
    user_id = _extract_user_info(current_user)
    logger.info(f"🟢 Creating marketing chat session for user {user_id}, report {request.report_id}")
    
    try:
        # Check session limit (same as reviews chat: 1 session per user)
        user_sessions = session_manager.get_user_sessions(user_id)
        if len(user_sessions) >= 1:
            raise HTTPException(
                status_code=429,
                detail="Maximum active sessions reached (1). Please close an existing session."
            )
        
        # Build context (includes ownership validation)
        # MCP mode: load only key_findings + recommendations + resumen_ejecutivo
        # Standard mode: load full context with all blocks and charts
        if settings.MCP_ENABLED:
            context = await marketing_context_builder.build_minimal_context(
                request.report_id,
                user_id
            )
            logger.info(f"MCP minimal context loaded for report {request.report_id}")
        else:
            context = await marketing_context_builder.build_context(
                request.report_id,
                user_id
            )
        
        # Create session using the generic session manager
        # We'll store report_id and agent_config_id in a way compatible with existing structure
        session = session_manager.create_session(
            user_id=user_id,
            id=request.report_id,  # Using id field to store report_id
            context=context
        )
        
        # Calculate expiration
        expires_at = session.created_at + timedelta(minutes=30)
        
        # Build period string
        data_window = context.get("data_window", {})
        report_period = None
        if data_window:
            date_from = data_window.get("date_from")
            date_to = data_window.get("date_to")
            if date_from and date_to:
                report_period = f"{date_from} to {date_to}"
        
        return CreateMarketingChatSessionResponse(
            session_id=session.session_id,
            report_id=request.report_id,
            agent_config_id=context.get("agent_config_id", "unknown"),
            report_period=report_period,
            created_at=session.created_at,
            expires_at=expires_at
        )
        
    except HTTPException:
        raise
    except BoomitAPIException as e:
        raise HTTPException(
            status_code=e.status_code,
            detail=e.message
        )
    except Exception as e:
        logger.error(f"Error creating marketing chat session: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to create marketing chat session"
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
    data: {"token": "El", "done": false}
    
    data: {"token": " CPA_FTD", "done": false}
    
    data: {"token": " promedio", "done": false}
    
    data: {"token": "", "done": true}
    ```
    """
    user_id = _extract_user_info(current_user)
    
    logger.info(
        f"User {user_id} sending message to marketing chat session {session_id}: "
        f"{request.message[:50]}..."
    )
    
    try:
        # Get session (validates ownership and expiration)
        session = session_manager.get_session(session_id, user_id)
        
        # Convert to MarketingChatSession for type safety
        marketing_session = MarketingChatSession(
            session_id=session.session_id,
            user_id=session.user_id,
            report_id=session.id,  # id is storing report_id
            agent_config_id=session.context.get("agent_config_id", "unknown"),
            context=session.context,
            messages=session.messages,
            created_at=session.created_at,
            last_activity=session.last_activity
        )
        
        # Add user message to session
        user_message = ChatMessage(
            role="user",
            content=request.message,
            timestamp=datetime.utcnow()
        )
        session_manager.add_message(session_id, user_message)
        
        # Stream AI response
        async def event_generator():
            """Generate SSE events from AI stream"""
            try:
                accumulated_response = ""
                
                # Stream tokens from OpenAI
                async for token in marketing_chat_service.stream_response(marketing_session, request.message):
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
                    f"Completed streaming response for marketing session {session_id}. "
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


@router.get("/sessions/{session_id}/messages", response_model=MarketingChatHistoryResponse)
async def get_conversation_history(
    session_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Get conversation history for a marketing chat session.
    
    Returns all messages in chronological order.
    """
    user_id = _extract_user_info(current_user)
    
    logger.info(f"User {user_id} retrieving history for marketing session {session_id}")
    
    try:
        # Get session (validates ownership and expiration)
        session = session_manager.get_session(session_id, user_id)
        
        return MarketingChatHistoryResponse(
            session_id=session.session_id,
            report_id=session.id,  # id is storing report_id
            agent_config_id=session.context.get("agent_config_id", "unknown"),
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
    Get marketing chat session statistics and metadata.
    
    Returns:
    - Message count
    - Session age
    - Report summary
    """
    user_id = _extract_user_info(current_user)
    
    try:
        session = session_manager.get_session(session_id, user_id)
        
        # Extract report summary
        context = session.context
        report_data = context.get("report_data", {})
        data_window = context.get("data_window", {})
        summary = report_data.get("summary", {})
        
        return {
            "session_id": session.session_id,
            "report_id": session.id,  # id is storing report_id
            "agent_config_id": context.get("agent_config_id", "unknown"),
            "message_count": len(session.messages),
            "created_at": session.created_at,
            "last_activity": session.last_activity,
            "age_minutes": (datetime.utcnow() - session.created_at).total_seconds() / 60,
            "report_summary": {
                "period": f"{data_window.get('date_from', 'N/A')} to {data_window.get('date_to', 'N/A')}",
                "blocks_count": len(report_data.get("blocks", [])),
                "key_findings_count": len(summary.get("key_findings", [])),
                "recommendations_count": len(summary.get("recommendations", []))
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
    List all active marketing chat sessions for the current user.
    
    Returns sessions sorted by last activity (most recent first).
    """
    user_id = _extract_user_info(current_user)
    
    try:
        sessions = session_manager.get_user_sessions(user_id)
        
        # Filter only marketing sessions (those with agent_config_id in context)
        marketing_sessions = [
            s for s in sessions
            if s.context.get("agent_config_id") is not None
        ]
        
        return {
            "total": len(marketing_sessions),
            "sessions": [
                {
                    "session_id": s.session_id,
                    "report_id": s.id,  # id is storing report_id
                    "agent_config_id": s.context.get("agent_config_id", "unknown"),
                    "message_count": len(s.messages),
                    "created_at": s.created_at,
                    "last_activity": s.last_activity
                }
                for s in marketing_sessions
            ]
        }
        
    except Exception as e:
        logger.error(f"Error listing marketing sessions: {e}")
        raise HTTPException(status_code=500, detail="Failed to list sessions")


@router.get("/health")
async def marketing_chat_health_check():
    """
    Health check endpoint for marketing chat service.
    
    Returns service status and cache statistics.
    """
    try:
        # Get session manager stats
        session_stats = session_manager.get_stats()
        
        # Get cache stats
        cache_stats = {
            "cached_reports": len(marketing_context_builder.cache.cache),
            "cache_ttl_minutes": marketing_context_builder.cache.ttl.total_seconds() / 60
        }
        
        return {
            "status": "healthy",
            "service": "marketing-chat",
            "session_stats": session_stats,
            "cache_stats": cache_stats
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "unhealthy",
            "service": "marketing-chat",
            "error": str(e)
        }
