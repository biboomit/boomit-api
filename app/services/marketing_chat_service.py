"""
Marketing Chat Service with OpenAI Integration

Handles AI-powered chat responses for marketing report analysis.
"""

import logging
from typing import AsyncGenerator, Dict, Any, List
from openai import AsyncOpenAI

from app.core.config import settings
from app.schemas.chat import ChatMessage
from app.schemas.marketing_chat import MarketingChatSession
from app.core.exceptions import BoomitAPIException

logger = logging.getLogger(__name__)


class MarketingChatService:
    """
    Service for AI-powered marketing report chat using OpenAI.
    
    Features:
    - Streaming responses token-by-token
    - Context-aware conversations about marketing reports
    - Campaign performance analysis
    - Metrics interpretation (FTD, CPA, CVR, inversión)
    """
    
    def __init__(self):
        """Initialize OpenAI client"""
        self.client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        self.model = getattr(settings, "OPENAI_CHAT_MODEL", "gpt-4o-mini")
        
        logger.info(f"MarketingChatService initialized with model: {self.model}")
    
    def _build_system_prompt(self, context: Dict[str, Any]) -> str:
        """
        Build system prompt with marketing report context.
        
        Creates a comprehensive system message that includes:
        - Role definition as marketing analytics expert
        - Report metadata and period
        - Key findings and recommendations
        - Block summaries (narratives and insights)
        - Marketing metrics glossary
        - Response guidelines
        """
        report_id = context.get("report_id", "unknown")
        agent_config = context.get("agent_config", {})
        report_data = context.get("report_data", {})
        data_window = context.get("data_window", {})
        
        # Extract key information
        company = agent_config.get("company", "Cliente")
        config_context = agent_config.get("config_context", {})
        
        # Build period string
        date_from = data_window.get("date_from", "N/A")
        date_to = data_window.get("date_to", "N/A")
        period_str = f"{date_from} a {date_to}"
        
        # Extract summary
        summary = report_data.get("summary", {})
        key_findings = summary.get("key_findings", [])
        recommendations = summary.get("recommendations", [])
        
        # Extract blocks
        blocks = report_data.get("blocks", [])
        
        # Build context summary
        context_summary = f"""
Eres un experto senior en Análisis de Marketing Digital y Performance de Campañas Publicitarias. 
Tu rol es ayudar a analizar e interpretar reportes de marketing, respondiendo preguntas sobre campañas, métricas y performance.

**Cliente:** {company}
**Reporte ID:** {report_id}
**Período analizado:** {period_str}

**Contexto de Negocio:**
"""
        
        # Add business context if available
        if config_context:
            objetivo = config_context.get("objetivoNegocio", "No especificado")
            metrica_exito = config_context.get("metricaExito", "No especificada")
            context_summary += f"- Objetivo de negocio: {objetivo}\n"
            context_summary += f"- Métrica de éxito: {metrica_exito}\n"
        
        context_summary += "\n**Hallazgos Clave del Reporte:**\n"
        
        # Add key findings
        if key_findings:
            for i, finding in enumerate(key_findings[:5], 1):
                context_summary += f"{i}. {finding}\n"
        else:
            context_summary += "No hay hallazgos clave disponibles.\n"
        
        context_summary += "\n**Recomendaciones Principales:**\n"
        
        # Add recommendations
        if recommendations:
            for i, rec in enumerate(recommendations[:5], 1):
                context_summary += f"{i}. {rec}\n"
        else:
            context_summary += "No hay recomendaciones disponibles.\n"
        
        context_summary += "\n**Secciones del Reporte Disponibles:**\n"
        
        # Add block summaries
        if blocks:
            for block in blocks:
                block_key = block.get("block_key", "unknown")
                narrative = block.get("narrative", "")
                insights = block.get("insights", [])
                charts = block.get("charts", [])
                
                # Translate block keys to human-readable names
                block_names = {
                    "resumen_ejecutivo": "Resumen Ejecutivo",
                    "resultados_generales": "Resultados Generales",
                    "analisis_por_region": "Análisis por Región",
                    "evolucion_conversiones": "Evolución de Conversiones",
                    "cvr_indices": "Índices de Conversión",
                    "proyecciones": "Proyecciones",
                    "aprendizajes": "Aprendizajes"
                }
                
                block_name = block_names.get(block_key, block_key.replace("_", " ").title())
                context_summary += f"\n**{block_name}:**\n"
                
                # Add narrative (truncated)
                if narrative:
                    narrative_preview = narrative[:300] + "..." if len(narrative) > 300 else narrative
                    context_summary += f"{narrative_preview}\n"
                
                # Add top insights
                if insights:
                    context_summary += "Insights clave:\n"
                    for insight in insights[:2]:  # Top 2 insights per block
                        insight_preview = insight[:150] + "..." if len(insight) > 150 else insight
                        context_summary += f"  - {insight_preview}\n"
                
                # Add charts with data
                if charts:
                    context_summary += "Gráficos y datos:\n"
                    for chart in charts:
                        chart_title = chart.get("chart_title", "Sin título")
                        chart_desc = chart.get("chart_description", "")
                        business_q = chart.get("business_question", "")
                        highcharts_spec = chart.get("highcharts_spec", {})
                        
                        context_summary += f"  📊 {chart_title}\n"
                        if chart_desc:
                            context_summary += f"     Descripción: {chart_desc}\n"
                        if business_q:
                            context_summary += f"     Pregunta de negocio: {business_q}\n"
                        
                        # Extract data from series
                        series_data = highcharts_spec.get("series", [])
                        if series_data:
                            context_summary += "     Datos:\n"
                            for serie in series_data[:3]:  # Limit to 3 series per chart
                                serie_name = serie.get("name", "Serie")
                                data_values = serie.get("data", [])
                                
                                # Format data preview (first and last values if many)
                                if isinstance(data_values, list) and len(data_values) > 0:
                                    if len(data_values) <= 5:
                                        data_str = str(data_values)
                                    else:
                                        data_str = f"[{data_values[0]}, {data_values[1]}, ..., {data_values[-1]}] ({len(data_values)} valores)"
                                    
                                    context_summary += f"       - {serie_name}: {data_str}\n"
                        
                        # Extract categories (x-axis labels) if present
                        xaxis_categories = highcharts_spec.get("xAxis", {})
                        if isinstance(xaxis_categories, dict):
                            categories = xaxis_categories.get("categories", [])
                            if categories and len(categories) > 0:
                                if len(categories) <= 5:
                                    cat_str = str(categories)
                                else:
                                    cat_str = f"[{categories[0]}, ..., {categories[-1]}] ({len(categories)} categorías)"
                                context_summary += f"     Categorías X: {cat_str}\n"
        else:
            context_summary += "No hay bloques de análisis disponibles.\n"
        
        # Add metrics glossary
        context_summary += """
**Glosario de Métricas de Marketing:**
- **Inversión**: Gasto publicitario total (USD)
- **Install**: Número de instalaciones generadas por la campaña
- **Apertura cuenta exitosa**: Registros completos después de instalar
- **FTD (First Time Deposit)**: Primer depósito de usuario - métrica crítica de conversión final
- **CPA_install**: Costo por instalación = inversión / install
- **CPA_apertura_cuenta_exitosa**: Costo por apertura exitosa = inversión / apertura_cuenta_exitosa
- **CPA_FTD**: Costo por primer depósito = inversión / FTD (KPI crítico)
- **CVR_install_FTD**: Tasa de conversión = FTD / install

**Funnel de Conversión:** Inversión → Install → Apertura → FTD

**Instrucciones de Respuesta:**
- Responde en español de manera clara, concisa y profesional
- Usa los datos del reporte para fundamentar tus respuestas
- Si una pregunta requiere datos no disponibles en el reporte, indícalo claramente
- Enfócate en insights accionables y recomendaciones prácticas
- Cuando hables de métricas, proporciona contexto y comparaciones cuando sea posible
- Prioriza análisis de performance, eficiencia de campañas y oportunidades de optimización
- Si el usuario pregunta por datos específicos de campañas, verifica si están en el reporte antes de responder
- Usa términos de marketing digital apropiados al nivel de expertise del usuario
- Sé objetivo y base tus respuestas en los datos del reporte
"""
        
        return context_summary
    
    def _prepare_messages(
        self,
        session: MarketingChatSession,
        user_message: str
    ) -> List[Dict[str, str]]:
        """
        Prepare messages for OpenAI API.
        
        Includes:
        - System prompt with report context
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
        session: MarketingChatSession,
        user_message: str
    ) -> AsyncGenerator[str, None]:
        """
        Stream AI response token-by-token.
        
        Args:
            session: MarketingChatSession with context and history
            user_message: New message from user
        
        Yields:
            Response tokens as they arrive
        
        Raises:
            BoomitAPIException: If OpenAI API call fails
        """
        messages = self._prepare_messages(session, user_message)
        
        logger.info(
            f"Streaming marketing chat response for session {session.session_id}, "
            f"report {session.report_id}, message history: {len(session.messages)} messages"
        )
        
        try:
            # Call OpenAI with streaming
            stream = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                stream=True,
                temperature=0.7,
                max_tokens=1500  # Slightly higher for marketing analysis
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
        session: MarketingChatSession,
        user_message: str
    ) -> str:
        """
        Get complete AI response (non-streaming).
        
        Useful for testing or when streaming is not needed.
        
        Args:
            session: MarketingChatSession with context and history
            user_message: New message from user
        
        Returns:
            Complete response text
        
        Raises:
            BoomitAPIException: If OpenAI API call fails
        """
        messages = self._prepare_messages(session, user_message)
        
        logger.info(
            f"Getting complete marketing chat response for session {session.session_id}, "
            f"report {session.report_id}, message history: {len(session.messages)} messages"
        )
        
        try:
            # Call OpenAI without streaming
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                stream=False,
                temperature=0.7,
                max_tokens=1500
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


# Global marketing chat service instance
marketing_chat_service = MarketingChatService()
