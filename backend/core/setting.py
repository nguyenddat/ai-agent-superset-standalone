from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    model_config = SettingsConfigDict(
        env_file= Path(__file__).resolve().parents[2] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # directory
    base_dir: Path = Path(__file__).resolve().parents[2]

    # database
    database_url: SecretStr | None = Field(default=None, validation_alias="DATABASE_URL")
    connection_encryption_key: SecretStr | None = Field(default=None, validation_alias="CONNECTION_ENCRYPTION_KEY")
    superset_url: str | None = Field(default=None, validation_alias="SUPERSET_URL")
    superset_username: str | None = Field(default=None, validation_alias="SUPERSET_USERNAME")
    superset_password: SecretStr | None = Field(default=None, validation_alias="SUPERSET_PASSWORD")
    own_knowledge_agent_key: SecretStr | None = Field(default=None, validation_alias="OWN_KNOWLEDGE_AGENT_KEY")
    own_knowledge_admin_key: SecretStr | None = Field(default=None, validation_alias="OWN_KNOWLEDGE_ADMIN_KEY")
    frontend_origin: str = Field(
        default="http://localhost:3000,http://127.0.0.1:3000", validation_alias="FRONTEND_ORIGIN"
    )

    # AI autofill
    openrouter_api_key: SecretStr | None = Field(default=None, validation_alias="OPENROUTER_API_KEY")
    openrouter_base_url: str = Field(default="https://openrouter.ai/api/v1", validation_alias="OPENROUTER_BASE_URL")
    openrouter_model: str = Field(default="openai/gpt-6-luna", validation_alias="OPENROUTER_MODEL")
    qdrant_url: str = Field(default="http://localhost:6333", validation_alias="QDRANT_URL")
    text2sql_collection: str = Field(default="text2sql_semantics_v1", validation_alias="TEXT2SQL_COLLECTION")
    text2sql_embedding_model: str = Field(
        default="openai/text-embedding-3-small",
        validation_alias="TEXT2SQL_EMBEDDING_MODEL",
    )
    text2sql_embedding_dimensions: int = Field(default=1536, validation_alias="TEXT2SQL_EMBEDDING_DIMENSIONS")
    text2sql_worker_concurrency: int = Field(default=4, ge=1, le=32, validation_alias="TEXT2SQL_WORKER_CONCURRENCY")
    text2sql_worker_poll_seconds: float = Field(default=2.0, gt=0, validation_alias="TEXT2SQL_WORKER_POLL_SECONDS")
    text2sql_job_max_attempts: int = Field(default=3, ge=1, validation_alias="TEXT2SQL_JOB_MAX_ATTEMPTS")
    text2sql_job_timeout_seconds: int = Field(default=900, ge=30, validation_alias="TEXT2SQL_JOB_TIMEOUT_SECONDS")
    text2sql_job_retention_days: int = Field(default=7, ge=1, validation_alias="TEXT2SQL_JOB_RETENTION_DAYS")
    text2sql_topic_intervals: str = Field(default="", validation_alias="TEXT2SQL_TOPIC_INTERVALS")
    text2sql_query_timeout_seconds: int = Field(
        default=15, ge=1, le=300, validation_alias="TEXT2SQL_QUERY_TIMEOUT_SECONDS"
    )
    text2sql_query_max_rows: int = Field(default=200, ge=1, le=5000, validation_alias="TEXT2SQL_QUERY_MAX_ROWS")
    text2sql_agent_max_rows_to_llm: int = Field(
        default=50, ge=1, le=1000, validation_alias="TEXT2SQL_AGENT_MAX_ROWS_TO_LLM"
    )
    text2sql_agent_max_steps: int = Field(default=12, ge=1, le=50, validation_alias="TEXT2SQL_AGENT_MAX_STEPS")
    text2sql_timezone: str = Field(default="Asia/Ho_Chi_Minh", validation_alias="TEXT2SQL_TIMEZONE")
    text2sql_clarification_ttl_minutes: int = Field(
        default=1440, ge=5, le=43200, validation_alias="TEXT2SQL_CLARIFICATION_TTL_MINUTES"
    )
    text2sql_chart_types_enabled: str = Field(default="", validation_alias="TEXT2SQL_CHART_TYPES_ENABLED")
    conversation_max_stored_rows: int = Field(
        default=200, ge=1, le=5000, validation_alias="CONVERSATION_MAX_STORED_ROWS"
    )
    text2sql_rerank_model: str = Field(default="typesafe/jev-1.14", validation_alias="TEXT2SQL_RERANK_MODEL")
    text2sql_rerank_pool: int = Field(default=20, ge=1, le=50, validation_alias="TEXT2SQL_RERANK_POOL")
    text2sql_rerank_concurrency: int = Field(default=8, ge=1, le=16, validation_alias="TEXT2SQL_RERANK_CONCURRENCY")
    text2sql_rerank_timeout_seconds: float = Field(
        default=20.0, gt=0, validation_alias="TEXT2SQL_RERANK_TIMEOUT_SECONDS"
    )

    @property
    def text2sql_chart_types(self) -> frozenset[str] | None:
        names = {name.strip() for name in self.text2sql_chart_types_enabled.split(",") if name.strip()}
        return frozenset(names | {"table"}) if names else None

    @property
    def frontend_origins(self) -> list[str]:
        return [origin.strip() for origin in self.frontend_origin.split(",") if origin.strip()]

    def require_database_url(self) -> str:
        if self.database_url is None or not self.database_url.get_secret_value().strip():
            raise RuntimeError("DATABASE_URL is required for database migrations and backend startup")
        return self.database_url.get_secret_value()

    def require_connection_encryption_key(self) -> str:
        if self.connection_encryption_key is None or not self.connection_encryption_key.get_secret_value().strip():
            raise RuntimeError("CONNECTION_ENCRYPTION_KEY is required to register source databases")
        return self.connection_encryption_key.get_secret_value()

    def require_openrouter_api_key(self) -> str:
        if self.openrouter_api_key is None or not self.openrouter_api_key.get_secret_value().strip():
            raise RuntimeError("OPENROUTER_API_KEY is required for AI autofill")
        return self.openrouter_api_key.get_secret_value()


config = Config()
