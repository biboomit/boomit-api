import logging
from typing import Dict, Type

from app.services.analytics_providers.base import AnalyticsProvider
from app.services.analytics_providers.takenos_provider import TakenosAnalyticsProvider
from app.services.analytics_providers.banco_bct_provider import BancoBctAnalyticsProvider

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Provider registry
# ---------------------------------------------------------------------------
# Maps provider identifiers to their implementation classes.
# To add a new provider:
#   1. Create a subclass of AnalyticsProvider in this package.
#   2. Add an entry here.
# ---------------------------------------------------------------------------
PROVIDERS: Dict[str, Type[AnalyticsProvider]] = {
    "takenos": TakenosAnalyticsProvider,
    "banco_bct": BancoBctAnalyticsProvider,
}


def get_analytics_provider(provider_name: str) -> AnalyticsProvider:
    """
    Factory function: returns an AnalyticsProvider instance for the given name.

    Args:
        provider_name: Identifier such as ``"takenos"`` or ``"banco_bct"``.
                       Looked up case-insensitively.

    Raises:
        ValueError: If the provider is not registered.
    """
    key = provider_name.strip().lower()
    provider_class = PROVIDERS.get(key)
    if provider_class is None:
        available = ", ".join(sorted(PROVIDERS.keys()))
        logger.error(
            f"❌ Analytics provider '{provider_name}' not supported. "
            f"Available: {available}"
        )
        raise ValueError(
            f"Analytics provider no soportado: '{provider_name}'. "
            f"Disponibles: {available}"
        )
    logger.info(f"🔌 Using analytics provider: {key} ({provider_class.__name__})")
    return provider_class()
