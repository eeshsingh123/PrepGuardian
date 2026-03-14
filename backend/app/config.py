import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # MongoDB
    MONGO_URI: str = "mongodb://localhost:27017"
    MONGO_DB_NAME: str = "prepguardian"

    # SQLite
    SQLITE_DB_PATH: str = "data/prepguardian.db"

    # ADK Agent
    AGENT_MODEL: str = "gemini-live-2.5-flash-native-audio"
    AGENT_NAME: str = "prepguardian_agent"
    APP_NAME: str = "prepguardian"
    RESPONSE_MODALITIES: list[str] = ["AUDIO"]

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


settings = Settings()

# The Google GenAI SDK and ADK read these directly from os.environ at runtime.
# Pydantic settings only stores them in the Python object — we must explicitly
# push them into the process environment so the SDK picks them up.
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "TRUE"
os.environ["GOOGLE_CLOUD_PROJECT"] = os.getenv("GOOGLE_CLOUD_PROJECT")
os.environ["GOOGLE_CLOUD_LOCATION"] = "us-central1"
