from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "OutboundOS"
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "INFO"
    benchmark_mode: bool = False

    database_url: str = "sqlite+aiosqlite:///./outboundos.db"
    redis_url: str = "redis://localhost:6379/0"
    redis_password: SecretStr | None = None

    openai_api_key: SecretStr | None = Field(default=None)
    openai_model: str = "gpt-4.1-mini"
    tavily_api_key: SecretStr | None = Field(default=None)
    exa_api_key: SecretStr | None = Field(default=None)
    firecrawl_api_key: SecretStr | None = Field(default=None)
    secrets_dir: str | None = "/run/secrets"

    service_name: str = "outboundos-api"
    otel_enabled: bool = True
    otel_exporter_otlp_endpoint: str | None = None

    rate_limit_per_minute: int = 120

    dashboard_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ]
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    _hydrate_secrets_from_dir(settings)
    return settings


def _hydrate_secrets_from_dir(settings: Settings) -> None:
    if not settings.secrets_dir:
        return

    secrets_path = Path(settings.secrets_dir)
    if not secrets_path.exists():
        return

    openai_secret_file = secrets_path / "openai_api_key"
    if settings.openai_api_key is None and openai_secret_file.exists():
        secret = openai_secret_file.read_text(encoding="utf-8").strip()
        settings.openai_api_key = SecretStr(secret)
