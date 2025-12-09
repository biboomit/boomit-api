"""
Session manager for in-memory chat session storage.

Note: This is a simple in-memory implementation suitable for development and small-scale deployments.
For production with multiple instances, migrate to Redis for shared session state.

Migration to Redis:
1. Install redis: pip install redis
2. Replace self.sessions dict with Redis client
3. Use Redis TTL for automatic expiration
4. Use Redis pub/sub for real-time updates across instances
"""

import uuid
from typing import Dict, Optional
from datetime import datetime, timedelta
import logging

from app.schemas.chat import ChatSession, ChatMessage
from app.core.exceptions import ChatSessionNotFoundError, ChatSessionExpiredError

logger = logging.getLogger(__name__)


class SessionManager:
    """
    Manages chat sessions with in-memory storage.
    
    Limitations:
    - Sessions are lost on server restart
    - Not shared across multiple server instances
    - Manual cleanup required for expired sessions
    
    For production, migrate to Redis for:
    - Persistent storage
    - Shared state across instances
    - Automatic TTL expiration
    """
    
    def __init__(self, session_ttl_minutes: int = 30, max_messages_per_session: int = 20):
        """
        Initialize session manager.
        
        Args:
            session_ttl_minutes: Session timeout in minutes (default: 30)
            max_messages_per_session: Maximum messages per session (default: 20)
        """
        self.sessions: Dict[str, ChatSession] = {}
        self.session_ttl = timedelta(minutes=session_ttl_minutes)
        self.max_messages = max_messages_per_session
        
        logger.info(
            f"SessionManager initialized: TTL={session_ttl_minutes}min, "
            f"MaxMessages={max_messages_per_session}"
        )
    
    def create_session(
        self,
        user_id: str,
        company_id: str,
        app_id: str,
        context: Dict
    ) -> ChatSession:
        """
        Create a new chat session.
        
        Args:
            user_id: User identifier
            company_id: Company identifier (for data isolation)
            app_id: App identifier
            context: Pre-loaded analysis context
        
        Returns:
            New ChatSession instance
        """
        session_id = f"session_{uuid.uuid4().hex}"
        
        session = ChatSession(
            session_id=session_id,
            user_id=user_id,
            company_id=company_id,
            app_id=app_id,
            context=context,
            messages=[],
            created_at=datetime.utcnow(),
            last_activity=datetime.utcnow()
        )
        
        self.sessions[session_id] = session
        
        logger.info(
            f"Created session {session_id} for user {user_id}, "
            f"company {company_id}, app {app_id}"
        )
        
        # Cleanup old sessions
        self._cleanup_expired_sessions()
        
        return session
    
    def get_session(self, session_id: str, user_id: str) -> ChatSession:
        """
        Get an existing session.
        
        Args:
            session_id: Session identifier
            user_id: User identifier (for ownership validation)
        
        Returns:
            ChatSession instance
        
        Raises:
            ChatSessionNotFoundError: If session doesn't exist
            ChatSessionExpiredError: If session has expired
            PermissionError: If user doesn't own the session
        """
        session = self.sessions.get(session_id)
        
        if not session:
            raise ChatSessionNotFoundError(f"Session {session_id} not found")
        
        # Validate ownership
        if session.user_id != user_id:
            logger.warning(
                f"User {user_id} attempted to access session {session_id} "
                f"owned by {session.user_id}"
            )
            raise PermissionError("You don't have permission to access this session")
        
        # Check expiration
        if self._is_session_expired(session):
            del self.sessions[session_id]
            raise ChatSessionExpiredError(
                f"Session {session_id} expired at "
                f"{session.last_activity + self.session_ttl}"
            )
        
        return session
    
    def add_message(self, session_id: str, message: ChatMessage) -> None:
        """
        Add a message to a session.
        
        Args:
            session_id: Session identifier
            message: ChatMessage to add
        
        Raises:
            ValueError: If message limit exceeded
        """
        session = self.sessions.get(session_id)
        
        if not session:
            raise ChatSessionNotFoundError(f"Session {session_id} not found")
        
        # Check message limit
        if len(session.messages) >= self.max_messages:
            raise ValueError(
                f"Session message limit reached ({self.max_messages}). "
                "Please create a new session."
            )
        
        session.messages.append(message)
        session.last_activity = datetime.utcnow()
        
        logger.debug(
            f"Added {message.role} message to session {session_id}. "
            f"Total messages: {len(session.messages)}"
        )
    
    def delete_session(self, session_id: str, user_id: str) -> None:
        """
        Delete a session.
        
        Args:
            session_id: Session identifier
            user_id: User identifier (for ownership validation)
        
        Raises:
            ChatSessionNotFoundError: If session doesn't exist
            PermissionError: If user doesn't own the session
        """
        session = self.sessions.get(session_id)
        
        if not session:
            raise ChatSessionNotFoundError(f"Session {session_id} not found")
        
        # Validate ownership
        if session.user_id != user_id:
            logger.warning(
                f"User {user_id} attempted to delete session {session_id} "
                f"owned by {session.user_id}"
            )
            raise PermissionError("You don't have permission to delete this session")
        
        del self.sessions[session_id]
        logger.info(f"Deleted session {session_id}")
    
    def get_user_sessions(self, user_id: str) -> list[ChatSession]:
        """
        Get all active sessions for a user.
        
        Args:
            user_id: User identifier
        
        Returns:
            List of ChatSession instances
        """
        user_sessions = [
            session for session in self.sessions.values()
            if session.user_id == user_id and not self._is_session_expired(session)
        ]
        
        return sorted(user_sessions, key=lambda s: s.last_activity, reverse=True)
    
    def _is_session_expired(self, session: ChatSession) -> bool:
        """Check if a session has expired based on TTL"""
        return datetime.utcnow() > (session.last_activity + self.session_ttl)
    
    def _cleanup_expired_sessions(self) -> None:
        """Remove expired sessions from storage"""
        expired_ids = [
            session_id for session_id, session in self.sessions.items()
            if self._is_session_expired(session)
        ]
        
        for session_id in expired_ids:
            del self.sessions[session_id]
        
        if expired_ids:
            logger.info(f"Cleaned up {len(expired_ids)} expired sessions")
    
    def get_stats(self) -> Dict:
        """Get session manager statistics"""
        total_sessions = len(self.sessions)
        total_messages = sum(len(s.messages) for s in self.sessions.values())
        
        return {
            "total_sessions": total_sessions,
            "total_messages": total_messages,
            "ttl_minutes": self.session_ttl.total_seconds() / 60,
            "max_messages_per_session": self.max_messages
        }


# Global session manager instance
session_manager = SessionManager(
    session_ttl_minutes=30,
    max_messages_per_session=20
)
