"""PRAGATI configuration. No secret has a default: SECRET_KEY / REFRESH_SECRET_KEY must be supplied."""
from functools import lru_cache
from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True, extra="ignore")

    APP_NAME: str = "PRAGATI"
    APP_ENV: str = "development"
    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str
    REFRESH_SECRET_KEY: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    COOKIE_SECURE: bool = False  # set true behind HTTPS

    DATABASE_URL: str = "sqlite+aiosqlite:///./pragati.db"
    REDIS_URL: str = ""          # optional: rate limiting + Celery broker
    CELERY_BROKER_URL: str = ""
    CELERY_RESULT_BACKEND: str = ""

    MODEL_PATH: str = "./models"
    VECTOR_DB_PATH: str = "./data/processed/doc_index"
    UPLOAD_DIR: str = "./data/uploads"
    REPORT_DIR: str = "./data/reports"
    MAX_UPLOAD_MB: int = 25

    CORS_ORIGINS: str = "http://localhost:5173"
    RISK_WEIGHTS_JSON: str = ""
    RATE_LIMIT_LOGIN_PER_MIN: int = 10

    LLM_PROVIDER: str = ""       # "" (disabled) | "groq"
    GROQ_API_KEY: str = ""

    @field_validator("SECRET_KEY", "REFRESH_SECRET_KEY")
    @classmethod
    def _strong(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError("secret keys must be at least 32 characters")
        return v

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
