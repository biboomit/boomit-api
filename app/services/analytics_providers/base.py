import csv
import json
import logging
import requests
from abc import ABC, abstractmethod
from io import StringIO
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode, urlparse, urlunparse

from app.integrations.gcp.identity_token_client import GCPIdentityTokenClient

logger = logging.getLogger(__name__)


class AnalyticsProvider(ABC):
    """
    Abstract base class for analytics data providers.

    Each provider encapsulates:
      - The URL of the analytics microservice for a specific company.
      - The logic to fetch, authenticate and parse analytics data (CSV).
      - A comprehensive explanation of the data format, dictionary and
        block-specific rules that is injected into the AI prompt as
        {analytics_explanation}.

    To add a new provider:
      1. Create a subclass in this package.
      2. Implement `service_url` (reads its own env var).
      3. Implement `analytics_explanation` (describes datasets, metrics,
         funnel and block rules for the AI).
      4. Register the subclass in factory.py.
    """

    def __init__(self):
        self.gcp_auth_client = GCPIdentityTokenClient()

    # ------------------------------------------------------------------
    # Abstract properties – each provider MUST implement these
    # ------------------------------------------------------------------

    @property
    @abstractmethod
    def service_url(self) -> str:
        """Base URL of the analytics microservice (from env var)."""
        ...

    @property
    @abstractmethod
    def analytics_explanation(self) -> str:
        """
        Comprehensive explanation of the data for this provider.

        Must include:
          - Data format: list of datasets and their structure.
          - Data dictionary: field/metric definitions.
          - Block-specific rules: which datasets/metrics to use per
            report block, mandatory charts and insights.

        This string is injected into the AI prompt via
        ``{analytics_explanation}``.
        """
        ...

    # ------------------------------------------------------------------
    # Overridable properties
    # ------------------------------------------------------------------

    @property
    def metrics_glossary(self) -> str:
        """
        Full metrics glossary injected into the standard chat system prompt.

        Override in each provider to match the client's specific funnel
        terminology (e.g. Install/FTD for Takenos, Visita Landing/Solicita TC
        Enviada for Banco BCT).
        """
        return (
            "\n**Glosario de Métricas de Marketing:**\n"
            "- **Inversión**: Gasto publicitario total (USD)\n"
            "- **CPA**: Costo por adquisición = inversión / conversiones (KPI crítico)\n"
            "\n**Funnel de Conversión:** Inversión → Conversión"
        )

    @property
    def metrics_glossary_compact(self) -> str:
        """
        Compact metrics glossary for MCP-enabled chat prompts.

        Override in each provider to match the client's specific funnel terminology.
        """
        return (
            "\n**Métricas clave:**\n"
            "- Inversión: gasto publicitario (USD)\n"
            "- CPA: costo por adquisición (KPI crítico)\n"
            "- Funnel: Inversión → Conversión"
        )

    @property
    def endpoint_path(self) -> str:
        """Path for the analytics CSV endpoint. Override if different."""
        return "/analytics/csv"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_analytics(
        self,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        top_n: int = 10,
    ) -> Tuple[List[Dict[str, Any]], Dict, str]:
        """
        Fetch analytics data from the provider's microservice.

        Returns:
            Tuple of ``(analytics_data, data_window, analytics_explanation)``
        """
        cls_name = self.__class__.__name__
        logger.info(
            f"📊 [{cls_name}] get_analytics IN "
            f"(date_from={date_from}, date_to={date_to}, top_n={top_n})"
        )

        final_url = self._build_url(date_from, date_to, top_n)
        logger.info(f"[{cls_name}] Calling microservice: {final_url}")

        headers = self._get_auth_headers()
        # log the final url and headers (without sensitive info)
        logger.debug(f"[{cls_name}] Request headers: {headers}")
        response = requests.get(final_url, headers=headers)

        if response.status_code != 200:
            logger.error(
                f"Error fetching analytics: {response.status_code} {response.text}"
            )
            raise RuntimeError(
                "No se pudo obtener datos analíticos del microservicio externo"
            )

        data_window = json.loads(response.headers.get("X-Data-Window", "{}"))
        analytics_data = self._parse_csv(response.content)

        logger.info(
            f"📊 [{cls_name}] get_analytics OUT: {len(analytics_data)} records"
        )
        return analytics_data, {"data_window": data_window}, self.analytics_explanation

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_url(
        self,
        date_from: Optional[str],
        date_to: Optional[str],
        top_n: int,
    ) -> str:
        base_raw = (self.service_url or "").strip()
        parsed = urlparse(base_raw)

        if not parsed.netloc:
            raise RuntimeError(
                f"{self.__class__.__name__}: service_url debe incluir esquema "
                f"y host, por ej. https://mi-servicio-..."
            )

        path = parsed.path or self.endpoint_path

        query_params: Dict[str, str] = {"top_n": str(top_n)}
        if date_from:
            query_params["date_from"] = date_from
        if date_to:
            query_params["date_to"] = date_to

        return urlunparse(
            (parsed.scheme, parsed.netloc, path, "", urlencode(query_params), "")
        )

    def _get_auth_headers(self) -> dict:
        parsed = urlparse(self.service_url)
        if parsed.scheme == "https":
            return self.gcp_auth_client.get_authorized_headers(self.service_url)
        return {}

    def _parse_csv(self, content: bytes) -> List[Dict[str, Any]]:
        try:
            logger.info(
                f"[CSV DEBUG] Decodificando respuesta CSV, tamaño: {len(content)} bytes"
            )
            csv_content = content.decode("utf-8")
            logger.info(f"[CSV DEBUG] Primeros 200 caracteres: {csv_content[:200]}")
            reader = csv.DictReader(StringIO(csv_content))
            logger.info(f"[CSV DEBUG] DictReader fieldnames: {reader.fieldnames}")
        except Exception as e:
            logger.error(f"[CSV ERROR] Error al preparar DictReader: {e}")
            raise

        analytics_data: List[Dict[str, Any]] = []
        for idx, row in enumerate(reader):
            logger.debug(f"[CSV DEBUG] Row {idx}: type={type(row)}, value={row}")
            if isinstance(row, dict) and any(row.values()):
                analytics_data.append(row)
            else:
                logger.warning(
                    f"[CSV WARNING] Skipping row {idx}: type={type(row)}, value={row}"
                )
        return analytics_data
