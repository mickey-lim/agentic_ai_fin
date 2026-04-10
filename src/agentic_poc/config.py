from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    """
    Centralized Configuration loading from .env or OS environment variables.
    """
    # Core API Keys
    GOOGLE_API_KEY: str = Field(default="")
    
    # LangSmith Observability
    LANGSMITH_TRACING: bool = Field(default=False)
    LANGSMITH_API_KEY: str = Field(default="")
    LANGSMITH_PROJECT: str = Field(default="default")
    
    # Security & auth
    JWT_SECRET: str
    ALLOWED_ORIGINS: List[str] = Field(default=["http://localhost:3000"])
    
    # Persistence
    CHECKPOINT_DB_PATH: str = Field(default="agentic_state.db")
    REGISTRY_DB_PATH: str = Field(default="agentic_registry.db")
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_parse_none_str="None"
    )

# Singleton instance
settings = Settings()
