class AppConstants:
    APP_NAME = "prepguardian"
    AGENT_NAME = "prepguardian_agent"
    INSIGHTS_APP_NAME = "prepguardian_insights"
    RESPONSE_MODALITIES = ["AUDIO"]
    DEFAULT_TARGET_COMPANY = "Top Tech Company"
    DEFAULT_TARGET_LEVEL = "Mid-level"


class ModelConstants:
    AGENT_LIVE_MODEL = "gemini-live-2.5-flash-native-audio"

    INSIGHT_PRO_MODEL = "gemini-3.1-pro-preview"
    INSIGHT_FLASH_MODEL = "gemini-3.1-flash-lite-preview"


class AuthConstants:
    JWT_ALGORITHM = "HS256"
    JWT_ISSUER = "prepguardian-api"
    ACCESS_TOKEN_TYPE = "access"
    ACCESS_TOKEN_EXPIRE_MINUTES = 30
    REFRESH_TOKEN_EXPIRE_DAYS = 14
    REFRESH_COOKIE_NAME = "pg_refresh_token"
    REFRESH_COOKIE_PATH = "/auth"
    MIN_PASSWORD_LENGTH = 8


class RedisConstants:
    ACTIVE_SESSION_PREFIX = "pg:live-session"
    REVOKED_ACCESS_TOKEN_PREFIX = "pg:revoked-access"
    ACTIVE_SESSION_TTL_SECONDS = 90
