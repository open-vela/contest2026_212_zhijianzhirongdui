"""Application configuration via environment variables."""

import os
from pathlib import Path

from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    # Application
    APP_NAME: str = "枢络 VelaMesh"
    APP_VERSION: str = os.getenv("APP_VERSION", "0.2.0")
    DEBUG: bool = os.getenv("DEBUG", "true").lower() == "true"

    # Server
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))
    STATIC_DIR: str = os.getenv("STATIC_DIR", str(BASE_DIR / "static"))
    LOG_DIR: str = os.getenv("LOG_DIR", "")

    # Database
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        # Legacy identifier kept on purpose: existing deployments already
        # hold data/dominiscius.db (project was formerly "Dominiscius").
        f"sqlite+aiosqlite:///{BASE_DIR}/data/dominiscius.db",
    )

    # JWT
    JWT_SECRET: str = os.getenv(
        "JWT_SECRET",
        "dev-secret-change-in-production-min-32-chars!!",
    )
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # MQTT
    MQTT_BROKER: str = os.getenv("MQTT_BROKER", "127.0.0.1")
    MQTT_PORT: int = int(os.getenv("MQTT_PORT", "1883"))
    # Legacy client-id spelling kept for broker ACL/back-compat.
    MQTT_CLIENT_ID: str = os.getenv("MQTT_CLIENT_ID", "dominiscius-server")
    MQTT_USERNAME: str = os.getenv("MQTT_USERNAME", "")  # set if broker requires auth
    MQTT_PASSWORD: str = os.getenv("MQTT_PASSWORD", "")
    MQTT_TOPIC_PREFIX: str = os.getenv("MQTT_TOPIC_PREFIX", "vela").strip("/")

    # Demo integration. Cloud upload requests always enter the local outbox
    # before a transport is attempted. Modes: disabled, mock, http.
    DEMO_NODE_ONLINE_SECONDS: int = int(os.getenv("DEMO_NODE_ONLINE_SECONDS", "15"))
    DEMO_SIMULATION_ENABLED: bool = os.getenv("DEMO_SIMULATION_ENABLED", "false").lower() == "true"
    DEMO_CLOUD_MODE: str = os.getenv("DEMO_CLOUD_MODE", "disabled").strip().lower()
    DEMO_CLOUD_ENDPOINT: str = os.getenv("DEMO_CLOUD_ENDPOINT", "")
    DEMO_CLOUD_TIMEOUT_SECONDS: float = float(os.getenv("DEMO_CLOUD_TIMEOUT_SECONDS", "5"))
    DEMO_CLOUD_MAX_RETRIES: int = int(os.getenv("DEMO_CLOUD_MAX_RETRIES", "5"))
    DEMO_CLOUD_BACKOFF_BASE_SECONDS: float = float(os.getenv("DEMO_CLOUD_BACKOFF_BASE_SECONDS", "1"))
    DEMO_CLOUD_BACKOFF_MAX_SECONDS: float = float(os.getenv("DEMO_CLOUD_BACKOFF_MAX_SECONDS", "60"))
    DEMO_CLOUD_WORKER_INTERVAL_SECONDS: float = float(os.getenv("DEMO_CLOUD_WORKER_INTERVAL_SECONDS", "1"))

    # CORS
    CORS_ORIGINS: list[str] = ["*"]

    # Seed
    SEED_DEFAULT_TENANT: str = os.getenv("SEED_DEFAULT_TENANT", "默认组织")
    SEED_ADMIN_USERNAME: str = os.getenv("SEED_ADMIN_USERNAME", "admin")
    SEED_ADMIN_PASSWORD: str = os.getenv("SEED_ADMIN_PASSWORD", "admin123")

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
