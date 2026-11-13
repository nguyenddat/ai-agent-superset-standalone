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
    frontend_origin: str = Field(
        default="http://localhost:3000,http://127.0.0.1:3000", validation_alias="FRONTEND_ORIGIN"
    )

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


config = Config()
