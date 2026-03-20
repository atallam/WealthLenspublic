"""
WealthLens OSS — Application Configuration
Reads from environment variables / .env file.
"""

from pydantic_settings import BaseSettings
from typing import Optional
import secrets


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "sqlite:///./wealthlens.db"

    # Security
    SECRET_KEY: str = secrets.token_urlsafe(48)
    ENCRYPTION_MASTER_SALT: str = secrets.token_urlsafe(32)
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 hours
    ALGORITHM: str = "HS256"

    # CORS
    ALLOWED_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

    # Google OAuth
    GOOGLE_CLIENT_ID: Optional[str] = None
    GOOGLE_CLIENT_SECRET: Optional[str] = None
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/api/auth/google/callback"

    # AI
    ANTHROPIC_API_KEY: Optional[str] = None

    # Cache (Redis)
    REDIS_URL: Optional[str] = None  # e.g. redis://redis:6379/0

    # Market Data — Twelve Data (free: 800/day)
    TWELVE_DATA_API_KEY: Optional[str] = None

    # Database pool tuning (PostgreSQL only)
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    ENVIRONMENT: str = "development"

    # Rate limiting
    RATE_LIMIT_PER_MINUTE: int = 60

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",")]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
