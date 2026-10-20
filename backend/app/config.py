import os
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_ENV: str = "development"

    # Models
    AGENT_LIVE_MODEL: str = "gemini-3.8-live"
    INSIGHT_PRO_MODEL: str = "gemini-3.1-pro-preview"
    INSIGHT_FLASH_MODEL: str = "gemini-3.1-flash-lite"

    # Live interview tuning
    LIVE_VOICE: str = "Charon"
    LIVE_COMPRESSION_TRIGGER_TOKENS: int = 32000
    LIVE_COMPRESSION_TARGET_TOKENS: int = 16000
    LIVE_VAD_SILENCE_DURATION_MS: int = 1200
    LIVE_VAD_END_OF_SPEECH_SENSITIVITY: Literal["LOW", "HIGH"] = "LOW"
    LIVE_VAD_PREFIX_PADDING_MS: int = 20

    # MongoDB
    MONGO_URI: str = "mongodb://localhost:27017"
    MONGO_DB_NAME: str = "prepguardian"

    # SQLite
    SQLITE_DB_PATH: str = "data/prepguardian.db"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Authentication
    JWT_SECRET_KEY: str = "dev-only-change-me-before-production"
    AUTH_COOKIE_SECURE: bool = False
    AUTH_COOKIE_SAMESITE: str = "lax"
    AUTH_COOKIE_DOMAIN: str | None = None

    # Vertex AI
    GOOGLE_CLOUD_PROJECT: str | None = None
    GOOGLE_CLOUD_LOCATION: str = "us-central1"

    # CORS
    CORS_ORIGINS: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

    @model_validator(mode="after")
    def validate_auth_settings(self):
        if self.APP_ENV.lower() == "production":
            if "JWT_SECRET_KEY" not in self.model_fields_set:
                raise ValueError(
                    "JWT_SECRET_KEY must be explicitly set in production."
                )
            if len(self.JWT_SECRET_KEY.strip()) < 32:
                raise ValueError(
                    "JWT_SECRET_KEY must be at least 32 characters in production."
                )
        return self


settings = Settings()

# The Google GenAI SDK and ADK read these directly from os.environ at runtime.
# Pydantic settings only stores them in the Python object — we must explicitly
# push them into the process environment so the SDK picks them up.
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "TRUE"
os.environ["GOOGLE_CLOUD_LOCATION"] = settings.GOOGLE_CLOUD_LOCATION
if settings.GOOGLE_CLOUD_PROJECT:
    os.environ["GOOGLE_CLOUD_PROJECT"] = settings.GOOGLE_CLOUD_PROJECT
