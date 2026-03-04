"""
Marketing Context Builder Service

Loads marketing report context from BigQuery for AI chat sessions.
Includes in-memory caching to reduce BigQuery queries.
"""

import logging
import json
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from google.cloud import bigquery
from app.services.analytics_providers.factory import get_analytics_provider
from app.core.exceptions import DatabaseConnectionError, BoomitAPIException
from app.core.config import bigquery_config

logger = logging.getLogger(__name__)


def _resolve_metrics_glossary(company_name: str):
    """
    Instantiate the analytics provider that corresponds to *company_name* and
    return ``(metrics_glossary, metrics_glossary_compact)``.

    Returns ``(None, None)`` when the provider cannot be resolved so that the
    chat service can fall back to its built-in defaults without crashing.
    """
    try:
        provider_key = company_name.strip().lower().replace(" ", "_")
        logger.info(f"\U0001f4d6 [GLOSSARY] Resolving metrics glossary for company='{company_name}' → provider_key='{provider_key}'")
        provider = get_analytics_provider(provider_key)
        glossary = provider.metrics_glossary
        glossary_compact = provider.metrics_glossary_compact
        logger.info(
            f"\u2705 [GLOSSARY] Resolved provider={type(provider).__name__}, "
            f"glossary_len={len(glossary) if glossary else 0}, "
            f"glossary_compact_len={len(glossary_compact) if glossary_compact else 0}"
        )
        logger.debug(f"[GLOSSARY] Full glossary preview: {glossary[:200] if glossary else 'None'}...")
        return glossary, glossary_compact
    except Exception as e:
        logger.warning(
            f"\u274c [GLOSSARY] Could not resolve analytics provider glossary for company "
            f"'{company_name}': {e}. Chat will use default glossary."
        )
        return None, None


class MarketingContextCache:
    """Simple in-memory cache for marketing contexts with TTL"""
    
    def __init__(self, ttl_minutes: int = 10):
        """
        Initialize cache.
        
        Args:
            ttl_minutes: Time-to-live for cached entries (default: 10 minutes)
        """
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.ttl = timedelta(minutes=ttl_minutes)
        logger.info(f"MarketingContextCache initialized with TTL={ttl_minutes} minutes")
    
    def get(self, report_id: str) -> Optional[Dict[str, Any]]:
        """Get cached context if not expired"""
        if report_id not in self.cache:
            return None
        
        entry = self.cache[report_id]
        
        # Check expiration
        if datetime.utcnow() > entry["expires_at"]:
            del self.cache[report_id]
            logger.debug(f"Cache expired for report {report_id}")
            return None
        
        logger.debug(f"Cache hit for report {report_id}")
        return entry["context"]
    
    def set(self, report_id: str, context: Dict[str, Any]) -> None:
        """Store context in cache with expiration"""
        self.cache[report_id] = {
            "context": context,
            "expires_at": datetime.utcnow() + self.ttl
        }
        logger.debug(f"Cached context for report {report_id}")
    
    def clear(self) -> None:
        """Clear all cached entries"""
        count = len(self.cache)
        self.cache.clear()
        logger.info(f"Cleared {count} cached entries")


class MarketingContextBuilder:
    """
    Builds context for marketing chat sessions by loading report data.
    
    Context includes:
    - Report JSON (blocks, summary, key_findings, recommendations)
    - Agent configuration (company, config_context, marketing_funnel, etc.)
    - Data window (period metadata)
    """
    
    def __init__(self):
        """Initialize BigQuery client and cache"""
        self.client = bigquery_config.get_client()
        self.reports_table = "marketing-dwh-specs.AIOutput.AI_MARKETING_REPORTS"
        self.agent_config_table = "marketing-dwh-specs.DWH.DIM_AI_REPORT_AGENT_CONFIGS"
        self.cache = MarketingContextCache(ttl_minutes=10)
        logger.info("MarketingContextBuilder initialized")
    
    async def build_context(
        self,
        report_id: str,
        user_id: str
    ) -> Dict[str, Any]:
        """
        Build chat context by loading report data.
        
        Args:
            report_id: Report identifier
            user_id: User identifier (for ownership validation)
        
        Returns:
            Dictionary with context data:
            {
                "report_id": "abc-123",
                "agent_config_id": "agent-456",
                "report_data": {
                    "blocks": [...],
                    "summary": {...}
                },
                "agent_config": {...},
                "data_window": {...},
                "report_generated_at": "2026-01-27T...",
                "context_generated_at": "2026-01-27T..."
            }
        
        Raises:
            BoomitAPIException: If report not found or access denied
            DatabaseConnectionError: If query fails
        """
        logger.info(f"Building context for report {report_id}, user {user_id}")
        
        # Check cache first
        cached_context = self.cache.get(report_id)
        if cached_context:
            # Validate ownership even for cached data
            if cached_context.get("user_id") != user_id:
                raise BoomitAPIException(
                    message="Access denied to this report",
                    status_code=403,
                    error_code="REPORT_ACCESS_DENIED"
                )
            return cached_context
        
        try:
            # Load report data
            report_data = await self._get_report_data(report_id, user_id)
            
            # Load agent configuration
            agent_config = await self._get_agent_config(report_data["agent_config_id"])
            
            # Parse report JSON
            report_json = json.loads(report_data["report_json"])
            
            # Resolve provider-specific metrics glossary
            metrics_glossary, metrics_glossary_compact = _resolve_metrics_glossary(
                agent_config.get("company", "")
            )

            logger.info(
                f"\U0001f4cb [CONTEXT-FULL] report={report_id}, company='{agent_config.get('company', '')}', "
                f"glossary_resolved={'YES' if metrics_glossary else 'NO (using default)'}, "
                f"blocks={len(report_json.get('blocks', []))}"
            )

            # Build context
            context = {
                "report_id": report_id,
                "agent_config_id": report_data["agent_config_id"],
                "user_id": user_id,  # Store for ownership validation in cache
                "report_data": report_json,
                "agent_config": agent_config,
                "data_window": report_data.get("data_window"),
                "metrics_glossary": metrics_glossary,
                "metrics_glossary_compact": metrics_glossary_compact,
                "report_generated_at": report_data["generated_at"].isoformat() if report_data.get("generated_at") else None,
                "context_generated_at": datetime.utcnow().isoformat()
            }
            
            # Cache the context
            self.cache.set(report_id, context)
            
            logger.info(
                f"Context built successfully for report {report_id}: "
                f"{len(report_json.get('blocks', []))} blocks, "
                f"period: {report_data.get('data_window', {}).get('date_from')} - "
                f"{report_data.get('data_window', {}).get('date_to')}"
            )
            
            return context
            
        except BoomitAPIException:
            raise
        except Exception as e:
            logger.error(f"Error building context: {e}")
            raise DatabaseConnectionError(
                f"Failed to build chat context for report {report_id}",
                details={"report_id": report_id, "error": str(e)}
            )
    
    async def build_minimal_context(
        self,
        report_id: str,
        user_id: str
    ) -> Dict[str, Any]:
        """
        Build lightweight context for MCP-enabled sessions.
        
        Loads only:
        - key_findings and recommendations (from summary)
        - resumen_ejecutivo block (high-level synthesis)
        - data_window (period metadata)
        - agent_config company and objectives
        
        All other blocks are fetched on-demand via MCP tools.
        This reduces session creation time and system prompt tokens (~800-1000 vs ~3000-5000).
        
        Args:
            report_id: Report identifier
            user_id: User identifier (for ownership validation)
        
        Returns:
            Minimal context dictionary
        """
        logger.info(f"Building minimal MCP context for report {report_id}, user {user_id}")

        # Check cache first (same cache as full context)
        cache_key = f"mcp_{report_id}"
        cached_context = self.cache.get(cache_key)
        if cached_context:
            if cached_context.get("user_id") != user_id:
                raise BoomitAPIException(
                    message="Access denied to this report",
                    status_code=403,
                    error_code="REPORT_ACCESS_DENIED"
                )
            return cached_context

        try:
            # Load report data (validates ownership)
            report_data = await self._get_report_data(report_id, user_id)

            # Load agent config (for company + objectives only=config_context + marketing funnel)
            agent_config = await self._get_agent_config(report_data["agent_config_id"])

            # Parse full JSON but extract only what we need
            report_json = json.loads(report_data["report_json"])
            summary = report_json.get("summary", {})
            blocks = report_json.get("blocks", [])

            # Extract only resumen_ejecutivo block
            resumen_block = None
            available_block_keys = []
            for block in blocks:
                bk = block.get("block_key", "")
                available_block_keys.append(bk)
                if bk == "resumen_ejecutivo":
                    resumen_block = block

            # Resolve provider-specific metrics glossary
            metrics_glossary, metrics_glossary_compact = _resolve_metrics_glossary(
                agent_config.get("company", "")
            )

            logger.info(
                f"\U0001f4cb [CONTEXT-MCP] report={report_id}, company='{agent_config.get('company', '')}', "
                f"glossary_resolved={'YES' if metrics_glossary else 'NO (using default)'}, "
                f"blocks_available={len(available_block_keys)}, "
                f"resumen_ejecutivo={'found' if resumen_block else 'missing'}"
            )

            # Build minimal context
            context = {
                "report_id": report_id,
                "agent_config_id": report_data["agent_config_id"],
                "user_id": user_id,
                "is_mcp": True,  # Flag to identify MCP sessions
                "data_window": report_data.get("data_window"),
                "company": agent_config.get("company", "Cliente"),
                "config_context": agent_config.get("config_context", {}),
                "marketing_funnel": agent_config.get("marketing_funnel", {}),
                "key_findings": summary.get("key_findings", []),
                "recommendations": summary.get("recommendations", []),
                "resumen_ejecutivo": resumen_block,
                "available_blocks": available_block_keys,
                "metrics_glossary": metrics_glossary,
                "metrics_glossary_compact": metrics_glossary_compact,
                "report_generated_at": (
                    report_data["generated_at"].isoformat()
                    if report_data.get("generated_at") else None
                ),
                "context_generated_at": datetime.utcnow().isoformat()
            }

            # Cache it
            self.cache.set(cache_key, context)

            logger.info(
                f"Minimal MCP context built for report {report_id}: "
                f"resumen_ejecutivo={'found' if resumen_block else 'missing'}, "
                f"{len(available_block_keys)} blocks available, "
                f"{len(summary.get('key_findings', []))} key findings"
            )

            return context

        except BoomitAPIException:
            raise
        except Exception as e:
            logger.error(f"Error building minimal context: {e}")
            raise DatabaseConnectionError(
                f"Failed to build minimal chat context for report {report_id}",
                details={"report_id": report_id, "error": str(e)}
            )

    async def _get_report_data(
        self,
        report_id: str,
        user_id: str
    ) -> Dict[str, Any]:
        """
        Get report data from AI_MARKETING_REPORTS table.
        
        Validates ownership and retrieves report JSON.
        """
        query = f"""
        SELECT
            report_id,
            agent_config_id,
            generated_at,
            report_json,
            user_id,
            date_from,
            date_to
        FROM `{self.reports_table}`
        WHERE report_id = @report_id
        LIMIT 1
        """
        
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("report_id", "STRING", report_id)
            ]
        )
        
        try:
            results = self.client.query(query, job_config=job_config).result()
            row = next(results, None)
         
            if not row:
                raise BoomitAPIException(
                    message=f"Report {report_id} not found",
                    status_code=404,
                    error_code="REPORT_NOT_FOUND"
                )
            
            # Validate ownership
            if row.user_id != user_id:
                logger.warning(
                    f"User {user_id} attempted to access report {report_id} "
                    f"owned by {row.user_id}"
                )
                raise BoomitAPIException(
                    message="Access denied to this report",
                    status_code=403,
                    error_code="REPORT_ACCESS_DENIED"
                )

            # Extract data_window from report metadata or first block
            data_window = None
            # extract data window from date_from and date_to present in row
            if row.date_from and row.date_to:
                data_window = {
                    "date_from": row.date_from,
                    "date_to": row.date_to
                }
            
            return {
                "report_id": row.report_id,
                "agent_config_id": row.agent_config_id,
                "generated_at": row.generated_at,
                "report_json": row.report_json,
                "data_window": data_window
            }
            
        except BoomitAPIException:
            raise
        except Exception as e:
            logger.error(f"Error fetching report data: {e}")
            raise DatabaseConnectionError(
                f"Failed to fetch report {report_id}",
                details={"report_id": report_id, "error": str(e)}
            )
    
    async def _get_agent_config(
        self,
        agent_config_id: str
    ) -> Dict[str, Any]:
        """
        Get agent configuration from DIM_AI_REPORT_AGENT_CONFIGS table.
        
        Returns configuration including company, config_context, etc.
        """
        query = f"""
        SELECT
            id,
            company,
            config_context,
            marketing_funnel
        FROM `{self.agent_config_table}`
        WHERE id = @agent_config_id
        LIMIT 1
        """
        
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("agent_config_id", "STRING", agent_config_id)
            ]
        )
        
        try:
            results = self.client.query(query, job_config=job_config).result()
            row = next(results, None)
            
            if not row:
                logger.warning(f"Agent config {agent_config_id} not found, using minimal config")
                return {
                    "agent_config_id": agent_config_id,
                    "company": "Unknown",
                    "config_context": {}
                }
            
            # Parse JSON fields
            config = {
                "agent_config_id": row.id,
                "company": row.company
            }
            
            # Parse JSON fields if they exist
            if row.config_context:
                config["config_context"] = json.loads(row.config_context) if isinstance(row.config_context, str) else row.config_context
            
            if row.marketing_funnel:
                config["marketing_funnel"] = json.loads(row.marketing_funnel) if isinstance(row.marketing_funnel, str) else row.marketing_funnel
            
            return config
            
        except Exception as e:
            logger.warning(f"Error fetching agent config: {e}")
            # Return minimal config on error
            return {
                "agent_config_id": agent_config_id,
                "company": "Unknown",
                "config_context": {}
            }


# Global context builder instance
marketing_context_builder = MarketingContextBuilder()
