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
