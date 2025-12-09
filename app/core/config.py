"""
Application configuration using Pydantic Settings v2
"""

import os
from typing import List, Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings
from functools import lru_cache
from google.cloud import bigquery
from app.integrations.openai.review_prompt import SYSTEM_PROMPT


class Settings(BaseSettings):
    """Application settings with environment variable support"""

    # Application Configuration
    APP_NAME: str = Field(default="Boomit AI API")
    VERSION: str = Field(default="1.0.0")
    ENVIRONMENT: str = Field(default="development")
    DEBUG: bool = Field(default=False)
    LOG_LEVEL: str = Field(default="INFO")

    # API Configuration
    API_V1_PREFIX: str = Field(default="/api/v1")
    HOST: str = Field(default="0.0.0.0")
    PORT: int = Field(default=8000)
    DEFAULT_PER_PAGE: int = Field(default=20)
    MAX_PER_PAGE: int = Field(default=100)
    DEFAULT_STATE: str = Field(default="ALL")

    # Security Configuration (as strings to avoid JSON parsing issues)
    ALLOWED_HOSTS: str = Field(default="*")
    CORS_ORIGINS: str = Field(default="*")

    # JWT Security - Updated for HS256
    SECRET_KEY: str = Field(default="your-very-secure-and-long-secret-key-here")
    ALGORITHM: str = Field(default="HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=30)
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=7)
    
    # WebSocket Configuration
    WEBSOCKET_AUTH_REQUIRED: bool = Field(default=True)

    # Auth0 Configuration - DEPRECATED (commented out)
    # AUTH0_DOMAIN: str = Field(default="your-auth0-domain")
    # AUTH0_AUDIENCE: str = Field(default="your-auth0-audience")
    # AUTH0_ALGORITHMS: str = Field(default="RS256")

    # Google Cloud Configuration
    GOOGLE_CLOUD_PROJECT: str = Field(default="your-gcp-project")
    GOOGLE_APPLICATION_CREDENTIALS: Optional[str] = Field(default=None)
    BIGQUERY_DATASET: str = Field(default="boomit_analytics")
    BIGQUERY_LOCATION: str = Field(default="US")

    # Database Configuration
    BQ_MAX_CONNECTIONS: int = Field(default=10)
    BQ_CONNECTION_TIMEOUT: int = Field(default=60)
    BQ_QUERY_TIMEOUT: int = Field(default=300)

    # Rate Limiting
    RATE_LIMIT_REQUESTS: int = Field(default=100)
    RATE_LIMIT_WINDOW: int = Field(default=60)

    # Pagination
    DEFAULT_PAGE_SIZE: int = Field(default=20)
    MAX_PAGE_SIZE: int = Field(default=100)

    # OpenAI Configuration
    OPENAI_API_KEY: str = Field(default="your-openai-api-key")
    OPENAI_BATCH_SIZE: int = Field(default=1)
    OPENAI_MODEL: str = Field(default="gpt-4o-mini")
    OPENAI_CHAT_MODEL: str = Field(default="gpt-4o-mini")  # Model for chat feature

    # File Upload Configuration
    MAX_FILE_SIZE: int = Field(default=10 * 1024 * 1024)  # 10MB
    ALLOWED_FILE_TYPES: str = Field(default="pdf,excel,csv")
    UPLOAD_DIRECTORY: str = Field(default="uploads")

    # External Services
    LOOKER_BASE_URL: Optional[str] = Field(default=None)
    LOOKER_CLIENT_ID: Optional[str] = Field(default=None)
    LOOKER_CLIENT_SECRET: Optional[str] = Field(default=None)

    # Monitoring & Observability
    SENTRY_DSN: Optional[str] = Field(default=None)
    ENABLE_METRICS: bool = Field(default=True)
    ENABLE_TRACING: bool = Field(default=True)
    METRICS_PORT: int = Field(default=9090)

    # Cache Configuration
    REDIS_URL: Optional[str] = Field(default=None)
    CACHE_TTL: int = Field(default=300)
    ENABLE_CACHE: bool = Field(default=False)

    # Email Configuration
    SMTP_HOST: Optional[str] = Field(default=None)
    SMTP_PORT: int = Field(default=587)
    SMTP_USERNAME: Optional[str] = Field(default=None)
    SMTP_PASSWORD: Optional[str] = Field(default=None)
    SMTP_TLS: bool = Field(default=True)
    FROM_EMAIL: str = Field(default="noreply@boomit.ai")

    # Documentation
    DOCS_URL: Optional[str] = Field(default="/docs")
    REDOC_URL: Optional[str] = Field(default="/redoc")
    OPENAPI_URL: str = Field(default="/openapi.json")

    # Validation
    @field_validator("ENVIRONMENT")
    @classmethod
    def validate_environment(cls, v):
        allowed = ["development", "staging", "production"]
        if v not in allowed:
            raise ValueError(f"ENVIRONMENT must be one of {allowed}, got: {v}")
        return v

    @field_validator("LOG_LEVEL")
    @classmethod
    def validate_log_level(cls, v):
        allowed = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in allowed:
            raise ValueError(f"LOG_LEVEL must be one of {allowed}, got: {v}")
        return v.upper()

    @field_validator("SECRET_KEY")
    @classmethod
    def validate_secret_key(cls, v):
        if len(v) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters long")
        return v

    @field_validator("PORT")
    @classmethod
    def validate_port(cls, v):
        if not 1 <= v <= 65535:
            raise ValueError("PORT must be between 1 and 65535")
        return v

    @field_validator("ALGORITHM")
    @classmethod
    def validate_algorithm(cls, v):
        allowed = ["HS256", "HS384", "HS512", "RS256", "RS384", "RS512"]
        if v not in allowed:
            raise ValueError(f"ALGORITHM must be one of {allowed}, got: {v}")
        return v

    # Helper methods to convert strings to lists
    def get_allowed_hosts(self) -> List[str]:
        """Convert ALLOWED_HOSTS string to list"""
        if self.ALLOWED_HOSTS == "*":
            return ["*"]
        return [host.strip() for host in self.ALLOWED_HOSTS.split(",") if host.strip()]

    def get_cors_origins(self) -> List[str]:
        """Convert CORS_ORIGINS string to list"""
        if self.CORS_ORIGINS == "*":
            return ["*"]
        return [
            origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()
        ]

    def get_allowed_file_types(self) -> List[str]:
        """Convert ALLOWED_FILE_TYPES string to list"""
        return [
            ft.strip().lower()
            for ft in self.ALLOWED_FILE_TYPES.split(",")
            if ft.strip()
        ]

    # Properties for convenience
    @property
    def is_development(self) -> bool:
        """Check if running in development environment"""
        return self.ENVIRONMENT == "development"

    @property
    def is_production(self) -> bool:
        """Check if running in production environment"""
        return self.ENVIRONMENT == "production"

    @property
    def is_staging(self) -> bool:
        """Check if running in staging environment"""
        return self.ENVIRONMENT == "staging"

    @property
    def database_url(self) -> str:
        """Get BigQuery connection string"""
        return f"bigquery://{self.GOOGLE_CLOUD_PROJECT}/{self.BIGQUERY_DATASET}"

    @property
    def docs_enabled(self) -> bool:
        """Check if documentation should be enabled"""
        return not self.is_production

    @property
    def reload_enabled(self) -> bool:
        """Check if auto-reload should be enabled"""
        return self.is_development

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
        "validate_assignment": True,
        "extra": "ignore",
    }


@lru_cache()
def get_settings() -> Settings:
    """
    Get cached settings instance.
    This ensures we don't read environment variables multiple times.
    """
    return Settings()


# Global settings instance
settings = get_settings()


# BigQuery table mappings for different environments
def get_bigquery_tables() -> dict:
    """Get BigQuery table names based on environment"""

    raise NotImplementedError("TODO: re-hacer funcion")
    base_dataset = settings.BIGQUERY_DATASET

    if settings.is_production:
        dataset = f"{base_dataset}_prod"
    elif settings.is_staging:
        dataset = f"{base_dataset}_staging"
    else:
        dataset = base_dataset

    return {
        "companies": f"{dataset}.companies",
        "projects": f"{dataset}.projects",
        "campaigns": f"{dataset}.campaigns",
        "report_agents": f"{dataset}.report_agents",
        "report_history": f"{dataset}.report_history",
        "optimization_groups": f"{dataset}.optimization_groups",
        "users": f"{dataset}.users",
        "user_permissions": f"{dataset}.user_permissions",
        "user_companies": f"{dataset}.user_companies",
        "audit_log": f"{dataset}.audit_log",
        "app_analysis": f"{dataset}.app_analysis",
        "app_reviews": f"{dataset}.app_reviews",
        "dashboards": f"{dataset}.dashboards",
        "target_events": f"{dataset}.target_events",
        "invitations": f"{dataset}.invitations",
    }


# Export commonly used configurations
# BIGQUERY_TABLES = get_bigquery_tables()


class BigQueryConfig:
    def __init__(self):
        self.project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
        self.dataset_id = os.getenv("BIGQUERY_DATASET")
        self.credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

        if self.credentials_path:
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = self.credentials_path

        self.client = bigquery.Client(project=self.project_id)

    def get_client(self):
        return self.client

    def get_table_id(self, table_name):
        return f"{self.project_id}.{self.dataset_id}.{table_name}"

    def get_table_id_with_dataset(self, dataset_id, table_name):
        return f"{self.project_id}.{dataset_id}.{table_name}"


# Instancia global de configuración
bigquery_config = BigQueryConfig()


class OpenAIConfig:
    def __init__(self):
        self.api_key = settings.OPENAI_API_KEY

    def get_api_key(self):
        return self.api_key

    def get_batch_size(self):
        return settings.OPENAI_BATCH_SIZE

    def get_model(self):
        return settings.OPENAI_MODEL

    def batch_system_prompt(self) -> str:
        return SYSTEM_PROMPT


# Development helpers
def print_config():
    """Print current configuration (for debugging)"""
    print("=== Boomit API Configuration ===")
    print(f"Environment: {settings.ENVIRONMENT}")
    print(f"Debug: {settings.DEBUG}")
    print(f"Host: {settings.HOST}:{settings.PORT}")
    print(f"JWT Algorithm: {settings.ALGORITHM}")
    print(f"Token Expiry: {settings.ACCESS_TOKEN_EXPIRE_MINUTES} minutes")
    print(f"GCP Project: {settings.GOOGLE_CLOUD_PROJECT}")
    print(f"BigQuery Dataset: {settings.BIGQUERY_DATASET}")
    print(f"Docs Enabled: {settings.docs_enabled}")
    print("================================")


if __name__ == "__main__":
    # Print configuration when run directly
    print_config()
