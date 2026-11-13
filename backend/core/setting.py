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
    def require_database_url(self) -> str:
        if self.database_url is None or not self.database_url.get_secret_value().strip():
            raise RuntimeError("DATABASE_URL is required for database migrations and backend startup")
        return self.database_url.get_secret_value()

config = Config()
