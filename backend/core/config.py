from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment / .env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = Field("development", alias="APP_ENV")
    log_level: str = Field("INFO", alias="LOG_LEVEL")
    max_planning_iterations: int = Field(4, alias="MAX_PLANNING_ITERATIONS")

    azure_openai_endpoint: str = Field(..., alias="AZURE_OPENAI_ENDPOINT")
    azure_openai_api_key: str = Field(..., alias="AZURE_OPENAI_API_KEY")
    azure_openai_deployment: str = Field(..., alias="AZURE_OPENAI_DEPLOYMENT")
    azure_openai_api_version: str = Field(
        "2024-10-21", alias="AZURE_OPENAI_API_VERSION"
    )
    azure_ai_project_connection_string: str | None = Field(
        None, alias="AZURE_AI_PROJECT_CONNECTION_STRING"
    )

    database_url: str = Field(..., alias="DATABASE_URL")


@lru_cache
def get_settings() -> Settings:
    return Settings() 
