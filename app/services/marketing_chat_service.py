"""
Marketing Chat Service with OpenAI Integration

Handles AI-powered chat responses for marketing report analysis.
"""

import logging
from app.integrations.mcp.host import MCPChatHost
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
        """Initialize OpenAI client (and MCP host if enabled)"""
        self.mcp_enabled = settings.MCP_ENABLED
        self.model = getattr(settings, "OPENAI_CHAT_MODEL", "gpt-4o-mini")
        
        if self.mcp_enabled:  # noqa: PLC0415
            self.mcp_host = MCPChatHost()
            logger.info(f"MarketingChatService initialized with MCP host, model: {self.model}")
        else:
            self.client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
            logger.info(f"MarketingChatService initialized with direct OpenAI, model: {self.model}")
    
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
        # Defensive checks for None values
        if context is None:
            logger.error("Context is None in _build_system_prompt")
            context = {}
        
        report_id = context.get("report_id", "unknown")
        agent_config = context.get("agent_config") or {}
        report_data = context.get("report_data") or {}
        data_window = context.get("data_window") or {}
        
        # Extract key information
        company = agent_config.get("company", "Cliente")
        config_context = agent_config.get("config_context") or {}
        
        # Build period string
        date_from = data_window.get("date_from", "N/A") if data_window else "N/A"
        date_to = data_window.get("date_to", "N/A") if data_window else "N/A"
        period_str = f"{date_from} a {date_to}"
        
        # Extract summary
        summary = report_data.get("summary") or {}
        key_findings = summary.get("key_findings") or []
        recommendations = summary.get("recommendations") or []
        
        # Extract blocks
        blocks = report_data.get("blocks") or []
        
        # Build context summary
        context_summary = f"""
Eres un analista de datos de marketing digital. Tu trabajo es responder preguntas
analizando EXCLUSIVAMENTE los datos del reporte proporcionado abajo.

Regla clave: SIEMPRE presenta primero los datos relevantes que el reporte SÍ contiene.
Si una parte de la pregunta requiere información que no está en el reporte, presenta
primero lo que sí puedes responder con datos, y luego indica qué parte no se puede
responder por falta de datos.

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
                        if not isinstance(chart, dict):
                            continue
                            
                        chart_title = chart.get("chart_title", "Sin título")
                        chart_desc = chart.get("chart_description", "")
                        business_q = chart.get("business_question", "")
                        highcharts_spec = chart.get("highcharts_spec") or {}
                        
                        context_summary += f"  📊 {chart_title}\n"
                        if chart_desc:
                            context_summary += f"     Descripción: {chart_desc}\n"
                        if business_q:
                            context_summary += f"     Pregunta de negocio: {business_q}\n"
                        
                        # Extract data from series
                        series_data = highcharts_spec.get("series") or []
                        if series_data:
                            context_summary += "     Datos:\n"
                            for serie in series_data[:3]:  # Limit to 3 series per chart
                                if not isinstance(serie, dict):
                                    continue
                                    
                                serie_name = serie.get("name", "Serie")
                                data_values = serie.get("data") or []
                                
                                # Format data preview (first and last values if many)
                                if isinstance(data_values, list) and len(data_values) > 0:
                                    if len(data_values) <= 5:
                                        data_str = str(data_values)
                                    else:
                                        data_str = f"[{data_values[0]}, {data_values[1]}, ..., {data_values[-1]}] ({len(data_values)} valores)"
                                    
                                    context_summary += f"       - {serie_name}: {data_str}\n"
                        
                        # Extract categories (x-axis labels) if present
                        xaxis_categories = highcharts_spec.get("xAxis") or {}
                        if isinstance(xaxis_categories, dict):
                            categories = xaxis_categories.get("categories") or []
                            if categories and len(categories) > 0:
                                if len(categories) <= 5:
                                    cat_str = str(categories)
                                else:
                                    cat_str = f"[{categories[0]}, ..., {categories[-1]}] ({len(categories)} categorías)"
                                context_summary += f"     Categorías X: {cat_str}\n"
        else:
            context_summary += "No hay bloques de análisis disponibles.\n"
        
        # Add metrics glossary (dynamic, provider-specific terminology)
        _default_glossary = (
            "\n**Glosario de Métricas de Marketing:**\n"
            "- **Inversión**: Gasto publicitario total (USD)\n"
            "- **Install**: Número de instalaciones generadas por la campaña\n"
            "- **Apertura cuenta exitosa**: Registros completos después de instalar\n"
            "- **FTD (First Time Deposit)**: Primer depósito de usuario - métrica crítica de conversión final\n"
            "- **CPA_install**: Costo por instalación = inversión / install\n"
            "- **CPA_apertura_cuenta_exitosa**: Costo por apertura exitosa = inversión / apertura_cuenta_exitosa\n"
            "- **CPA_FTD**: Costo por primer depósito = inversión / FTD (KPI crítico)\n"
            "- **CVR_install_FTD**: Tasa de conversión = FTD / install\n"
            "\n**Funnel de Conversión:** Inversión → Install → Apertura → FTD"
        )
        resolved_glossary = context.get("metrics_glossary")
        using_provider_glossary = resolved_glossary is not None
        context_summary += resolved_glossary or _default_glossary
        logger.info(
            f"\U0001f4d6 [SYSTEM-PROMPT] report={report_id}, "
            f"glossary_source={'PROVIDER' if using_provider_glossary else 'DEFAULT (Takenos)'}, "
            f"glossary_len={len(resolved_glossary) if resolved_glossary else len(_default_glossary)}"
        )

        context_summary += """

**REGLA #1 — SIEMPRE MOSTRAR DATOS PRIMERO:**
Antes de decir "no hay datos", busca qué datos del reporte SÍ son relevantes para la pregunta.
Presenta esos datos con valores específicos (números, nombres de campañas, networks, fechas).
Después de presentar los datos disponibles, si la pregunta pide algo más que no está en el reporte,
di: "El reporte no contiene datos sobre [X], por lo que esa parte no se puede evaluar."

**REGLA #2 — NO RELLENAR CON TEORÍA:**
Después de presentar los datos y declarar los límites, PARA. No agregues:
- Consejos genéricos ("diversificar canales", "pruebas A/B", "remarketing", "segmentación diferente",
  "reconocimiento de marca", "optimizar la landing", "analizar el público").
- Especulaciones sobre lo que "podría" pasar sin datos que lo soporten.
- Puntos numerados que no citan datos del reporte.
Si terminaste de analizar los datos y no hay más que decir, la respuesta termina ahí.

**REGLA #3 — FORMATO:**
- Responde en español, claro y profesional.
- "Mejor CPA" = valor más BAJO. "Peor CPA" = valor más ALTO.
- Una respuesta corta con datos concretos es mejor que una larga con relleno.
"""

        return context_summary
    
    def _build_system_prompt_mcp(self, context: Dict[str, Any]) -> str:
        """
        Build lightweight system prompt for MCP-enabled sessions.
        
        Only includes pre-loaded context (key_findings, recommendations,
        resumen_ejecutivo). Other data is fetched on-demand via MCP tools.
        ~50 lines vs ~200 lines of the full prompt.
        """
        if context is None:
            context = {}

        report_id = context.get("report_id", "unknown")
        company = context.get("company", "Cliente")
        config_context = context.get("config_context") or {}
        data_window = context.get("data_window") or {}
        key_findings = context.get("key_findings") or []
        recommendations = context.get("recommendations") or []
        resumen_block = context.get("resumen_ejecutivo")
        available_blocks = context.get("available_blocks") or []

        date_from = data_window.get("date_from", "N/A")
        date_to = data_window.get("date_to", "N/A")
        period_str = f"{date_from} a {date_to}"

        prompt = f"""Eres un analista de datos de marketing digital. Tu trabajo es responder preguntas
analizando EXCLUSIVAMENTE los datos del reporte proporcionado.

Regla clave: SIEMPRE presenta primero los datos relevantes que el reporte SÍ contiene.
Si una parte de la pregunta requiere información que no está en el reporte, presenta
primero lo que sí puedes responder con datos, y luego indica qué parte no se puede
responder por falta de datos.

**Cliente:** {company}
**Reporte ID:** {report_id}
**Período analizado:** {period_str}
"""

        # Business context
        if config_context:
            objetivo = config_context.get("objetivoNegocio", "No especificado")
            metrica = config_context.get("metricaExito", "No especificada")
            prompt += f"\n**Contexto de Negocio:**\n- Objetivo: {objetivo}\n- Métrica de éxito: {metrica}\n"

        # Pre-loaded key findings
        if key_findings:
            prompt += "\n**Hallazgos Clave del Reporte:**\n"
            for i, finding in enumerate(key_findings[:5], 1):
                prompt += f"{i}. {finding}\n"

        # Pre-loaded recommendations
        if recommendations:
            prompt += "\n**Recomendaciones Principales:**\n"
            for i, rec in enumerate(recommendations[:5], 1):
                prompt += f"{i}. {rec}\n"

        # Pre-loaded resumen_ejecutivo block
        if resumen_block:
            prompt += "\n**Resumen Ejecutivo (pre-cargado):**\n"
            narrative = resumen_block.get("narrative", "")
            if narrative:
                prompt += f"{narrative}\n"
            insights = resumen_block.get("insights", [])
            if insights:
                prompt += "Insights:\n"
                for insight in insights[:3]:
                    prompt += f"  - {insight}\n"

        # Available blocks for tool calls
        block_names = {
            "resumen_ejecutivo": "Resumen Ejecutivo",
            "resultados_generales": "Resultados Generales",
            "analisis_por_region": "Análisis por Región",
            "evolucion_conversiones": "Evolución de Conversiones",
            "cvr_indices": "Índices de Conversión",
            "proyecciones": "Proyecciones",
            "aprendizajes": "Aprendizajes"
        }
        prompt += "\n**Secciones disponibles para consulta (usa las herramientas para obtener datos):**\n"
        for bk in available_blocks:
            display = block_names.get(bk, bk.replace("_", " ").title())
            prompt += f"  - {display} (block_key: '{bk}')\n"

        # Metrics glossary (compact, provider-specific)
        resolved_compact = context.get("metrics_glossary_compact")
        _default_compact = (
            "\n**Métricas clave:**\n"
            "- Inversión: gasto publicitario (USD)\n"
            "- Install: instalaciones\n"
            "- Apertura cuenta exitosa: registros completos\n"
            "- FTD: primer depósito (KPI crítico)\n"
            "- CPA_FTD: costo por FTD = inversión / FTD\n"
            "- CVR_install_FTD: tasa conversión = FTD / install\n"
            "- Funnel: Inversión → Install → Apertura → FTD"
        )
        using_provider = resolved_compact is not None
        prompt += resolved_compact or _default_compact
        logger.info(
            f"\U0001f4d6 [SYSTEM-PROMPT-MCP] report={report_id}, "
            f"glossary_source={'PROVIDER' if using_provider else 'DEFAULT (Takenos)'}, "
            f"glossary_compact_len={len(resolved_compact) if resolved_compact else len(_default_compact)}"
        )

        prompt += """

**REGLA #1 — SIEMPRE MOSTRAR DATOS PRIMERO:**
Antes de decir "no hay datos", busca qué datos del reporte SÍ son relevantes para la pregunta.
Presenta esos datos con valores específicos (números, nombres de campañas, networks, fechas).
Después de presentar los datos disponibles, si la pregunta pide algo más que no está en el reporte,
di: "El reporte no contiene datos sobre [X], por lo que esa parte no se puede evaluar."

**REGLA #2 — NO RELLENAR CON TEORÍA:**
Después de presentar los datos y declarar los límites, PARA. No agregues:
- Consejos genéricos ("diversificar canales", "pruebas A/B", "remarketing", "segmentación diferente",
  "reconocimiento de marca", "optimizar la landing", "analizar el público").
- Especulaciones sobre lo que "podría" pasar sin datos que lo soporten.
- Puntos numerados que no citan datos del reporte.
Si terminaste de analizar los datos y no hay más que decir, la respuesta termina ahí.

**REGLA #3 — FORMATO Y HERRAMIENTAS:**
- Responde en español, claro y profesional.
- SIEMPRE usa herramientas antes de responder con datos numéricos.
- Para bloques específicos usa tool_get_report_blocks.
- "Mejor CPA" = valor más BAJO. "Peor CPA" = valor más ALTO.
- Una respuesta corta con datos concretos es mejor que una larga con relleno.
"""
        logger.debug(f"Built MCP system prompt for report {report_id}:\n{prompt}")
        return prompt

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
        
        # Use MCP-specific prompt if MCP is enabled
        if self.mcp_enabled:
            system_prompt = self._build_system_prompt_mcp(session.context)
        else:
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
            f"report {session.report_id}, message history: {len(session.messages)} messages, "
            f"mcp_enabled: {self.mcp_enabled}"
        )
        
        # MCP path: use MCPChatHost with tool-calling loop
        if self.mcp_enabled:
            try:
                user_id = session.user_id
                async for token in self.mcp_host.stream_with_tools(messages, user_id):
                    yield token
                
                logger.info(f"MCP streaming completed for session {session.session_id}")
                
            except BoomitAPIException:
                raise
            except Exception as e:
                logger.error(f"MCP streaming error: {type(e).__name__}: {e}", exc_info=True)
                raise BoomitAPIException(
                    message="Failed to generate AI response",
                    status_code=500,
                    error_code="MCP_AI_GENERATION_ERROR",
                    details={"error": repr(e)}
                )
            return
        
        # Original path: direct OpenAI streaming (when MCP_ENABLED=false)
        try:
            # Call OpenAI with streaming
            stream = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                stream=True,
                temperature=0.2,
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
                temperature=0.2,
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
