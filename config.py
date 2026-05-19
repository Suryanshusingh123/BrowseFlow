from pydantic_settings import BaseSettings
from pydantic import Field
from functools import lru_cache


class Settings(BaseSettings):
    """
    All configuration loaded from environment variables.
    pydantic-settings automatically reads from .env file.
    """

    # AI configuration
    gemini_api_key: str = Field(default="", alias="GEMINI_API_KEY")
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    ai_provider: str = Field(default="gemini", alias="AI_PROVIDER")

    # Browser configuration
    browser_headless: bool = Field(default=False, alias="BROWSER_HEADLESS")
    browser_slow_mo: int = Field(default=50, alias="BROWSER_SLOW_MO")

    # App configuration
    debug: bool = Field(default=True, alias="DEBUG")

    class Config:
        env_file = ".env"          # tells pydantic-settings to load this file
        env_file_encoding = "utf-8"
        case_sensitive = False     # GEMINI_API_KEY and gemini_api_key both work


@lru_cache()
def get_settings() -> Settings:
    """
    Returns a cached Settings instance.

    Why lru_cache? Settings are read from disk/env on creation.
    We don't want to re-read them on every function call.
    The cache is invalidated if you restart the process.
    """
    return Settings()
