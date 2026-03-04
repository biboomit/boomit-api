"""
Chat service with OpenAI integration.

Handles AI-powered chat responses using OpenAI's Chat API with streaming support.
"""

import logging
import json
from typing import AsyncGenerator, Dict, Any, List
from openai import AsyncOpenAI

from app.core.config import settings
from app.schemas.chat import ChatMessage, ChatSession
from app.core.exceptions import BoomitAPIException

logger = logging.getLogger(__name__)


class ChatService:
    """
    Service for AI-powered chat using OpenAI.
    
    Features:
    - Streaming responses token-by-token
    - Context-aware conversations
    - Message history management
    """
    
    def __init__(self):
        """Initialize OpenAI client"""
        self.client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        self.model = getattr(settings, "OPENAI_CHAT_MODEL", "gpt-4o-mini")
        
        logger.info(f"ChatService initialized with model: {self.model}")
    
    def _build_system_prompt(self, context: Dict[str, Any]) -> str:
        """
        Build system prompt with loaded context.
        
        Creates a comprehensive system message that includes:
        - Role definition
        - Available analysis data
        - Response guidelines
        """
        app_id = context.get("app_id", "unknown")
        stats = context.get("stats", {})
        sentiment = context.get("sentiment_summary", {})
        themes = context.get("emerging_themes", [])
        samples = context.get("sample_reviews", {})
        
        # Build context summary
        context_summary = f"""
Eres un asistente de análisis de reviews de aplicaciones móviles. Tu rol es ayudar a analizar y responder preguntas sobre las reviews de la aplicación.

**App analizada:** {app_id}
**Período de análisis:** Últimos {stats.get('period_days', 30)} días
**Total de reviews:** {stats.get('total_reviews', 0)}
**Rating promedio:** {stats.get('avg_rating', 0):.2f}/5.0

**Resumen de Sentimiento:**
"""
        
        # Add sentiment data if available
        if sentiment:
            if isinstance(sentiment, dict):
                for key, value in sentiment.items():
                    context_summary += f"- {key}: {value}\n"
            else:
                context_summary += f"{sentiment}\n"
        else:
            context_summary += "No hay datos de sentimiento disponibles.\n"
        
        context_summary += "\n**Temas Emergentes:**\n"
        
        # Add themes if available
        if themes:
            for i, theme in enumerate(themes[:5], 1):  # Top 5 themes
                if isinstance(theme, dict):
                    theme_name = theme.get("theme", theme.get("name", "Tema"))
                    count = theme.get("count", "N/A")
                    context_summary += f"{i}. {theme_name} (menciones: {count})\n"
                else:
                    context_summary += f"{i}. {theme}\n"
        else:
            context_summary += "No hay temas emergentes identificados.\n"
        
        context_summary += "\n**Ejemplos de Reviews Positivas:**\n"
        
        # Add positive review samples
        positive_reviews = samples.get("positive", [])
        if positive_reviews:
            for i, review in enumerate(positive_reviews[:3], 1):  # Top 3
                text = review.get("text", "")
                rating = review.get("rating", "N/A")
                # Truncate long reviews
                text_preview = text[:150] + "..." if len(text) > 150 else text
                context_summary += f"{i}. [{rating}⭐] {text_preview}\n"
        else:
            context_summary += "No hay reviews positivas disponibles.\n"
        
        context_summary += "\n**Ejemplos de Reviews Negativas:**\n"
        
        # Add negative review samples
        negative_reviews = samples.get("negative", [])
        if negative_reviews:
            for i, review in enumerate(negative_reviews[:3], 1):  # Top 3
                text = review.get("text", "")
                rating = review.get("rating", "N/A")
                text_preview = text[:150] + "..." if len(text) > 150 else text
                context_summary += f"{i}. [{rating}⭐] {text_preview}\n"
        else:
            context_summary += "No hay reviews negativas disponibles.\n"
        
        # Add guidelines
        context_summary += """
**Instrucciones:**
- Responde en español de manera clara y concisa
- Usa los datos de contexto para fundamentar tus respuestas
- Si no tienes información suficiente, indícalo claramente
- Mantén un tono profesional y objetivo
- Prioriza insights accionables y recomendaciones prácticas
- Si el usuario pregunta por datos numéricos específicos, usa las estadísticas disponibles
- Enfócate en análisis de negocio y experiencia de usuario
"""
        
        return context_summary
    
    def _prepare_messages(
        self,
        session: ChatSession,
        user_message: str
    ) -> List[Dict[str, str]]:
        """
        Prepare messages for OpenAI API.
        
        Includes:
        - System prompt with context
        - Conversation history
        - New user message
        """
        messages = []
        
        # Add system prompt with context
        system_prompt = self._build_system_prompt(session.context)
        messages.append({
            "role": "system",
            "content": system_prompt
        })
        
        # Add conversation history
        for msg in session.messages:
            messages.append({
                "role": msg.role,
                "content": msg.content
            })
        
        # Add new user message
        messages.append({
            "role": "user",
            "content": user_message
        })
        
        return messages
    
    async def stream_response(
        self,
        session: ChatSession,
        user_message: str
    ) -> AsyncGenerator[str, None]:
        """
        Stream AI response token-by-token.
        
        Args:
            session: ChatSession with context and history
            user_message: New message from user
        
        Yields:
            Response tokens as they arrive
        
        Raises:
            BoomitAPIException: If OpenAI API call fails
        """
        messages = self._prepare_messages(session, user_message)
        
        logger.info(
            f"Streaming response for session {session.session_id}, "
            f"message history: {len(session.messages)} messages"
        )
        
        try:
            # Call OpenAI with streaming
            stream = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                stream=True,
                temperature=0.7,
                max_tokens=1000
            )
            
            # Stream tokens
            async for chunk in stream:
                # Extract content delta
                if chunk.choices and len(chunk.choices) > 0:
                    delta = chunk.choices[0].delta
                    if delta.content:
                        yield delta.content
            
            logger.info(f"Streaming completed for session {session.session_id}")
            
        except Exception as e:
            logger.error(f"OpenAI streaming error: {e}")
            raise BoomitAPIException(
                message="Failed to generate AI response",
                status_code=500,
                error_code="AI_GENERATION_ERROR",
                details={"error": str(e)}
            )
    
    async def get_complete_response(
        self,
        session: ChatSession,
        user_message: str
    ) -> str:
        """
        Get complete AI response (non-streaming).
        
        Useful for testing or when streaming is not needed.
        
        Args:
            session: ChatSession with context and history
            user_message: New message from user
        
        Returns:
            Complete response text
        
        Raises:
            BoomitAPIException: If OpenAI API call fails
        """
        messages = self._prepare_messages(session, user_message)
        
        logger.info(
            f"Getting complete response for session {session.session_id}, "
            f"message history: {len(session.messages)} messages"
        )
        
        try:
            # Call OpenAI without streaming
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                stream=False,
                temperature=0.7,
                max_tokens=1000
            )
            
            # Extract response text
            if response.choices and len(response.choices) > 0:
                content = response.choices[0].message.content
                logger.info(f"Response generated for session {session.session_id}")
                return content
            
            raise BoomitAPIException(
                message="No response generated",
                status_code=500,
                error_code="EMPTY_RESPONSE"
            )
            
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            raise BoomitAPIException(
                message="Failed to generate AI response",
                status_code=500,
                error_code="AI_GENERATION_ERROR",
                details={"error": str(e)}
            )


# Global chat service instance
chat_service = ChatService()
