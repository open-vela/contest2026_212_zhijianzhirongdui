"""Application configuration via environment variables."""

import os
from pathlib import Path

from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parent.parent


def _env(name: str, default: str | None = None) -> str | None:
    """Read a VELAMESH_ setting with legacy DOMINISCIUS_ prefix fallback.

    The codebase was formerly named "Dominiscius". New hub-era variables use
    the VELAMESH_ prefix; old DOMINISCIUS_-prefixed deployments keep working.
    """
    return os.getenv(name, os.getenv(name.replace("VELAMESH_", "DOMINISCIUS_", 1), default))


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
    # Hub-era edge contract: edge/<id>/{face,gait,ble,status} + hub/<id>/cmd.
    # Default prefix "edge" matches the issue spec; the legacy vela/ and
    # dominiscius/ firmware topics stay subscribed for back-compat.
    MQTT_EDGE_TOPIC_PREFIX: str = os.getenv("MQTT_EDGE_TOPIC_PREFIX", "edge").strip("/")
    # auto (default): probe MQTT_BROKER, fall back to the in-process broker so
    # run.sh works on a bare demo laptop without EMQX/mosquitto. Other values:
    # external (require the configured broker), embedded (always local).
    MQTT_MODE: str = (_env("VELAMESH_MQTT_MODE", "auto") or "auto").strip().lower()
    MQTT_CONNECT_TIMEOUT: float = float(_env("VELAMESH_MQTT_CONNECT_TIMEOUT", "2") or 2)
    MQTT_EMBEDDED_LISTEN_HOST: str = _env("VELAMESH_MQTT_EMBEDDED_HOST", "127.0.0.1")
    MQTT_EMBEDDED_LISTEN_PORT: int = int(_env("VELAMESH_MQTT_EMBEDDED_PORT", "11883"))

    # MiMo cloud model (Xiaomi MiMo). API key ONLY via environment; never put
    # a real key in the repo. Blank/unset => deterministic local mock.
    MIMO_API_KEY: str = _env("VELAMESH_MIMO_API_KEY", "") or ""
    MIMO_BASE_URL: str = _env(
        "VELAMESH_MIMO_BASE_URL", "https://api.mimo.xiaomi.com/v1"
    )
    MIMO_MODEL: str = _env("VELAMESH_MIMO_MODEL", "mimo-vl-7b") or "mimo-vl-7b"
    MIMO_TIMEOUT_SECONDS: float = float(_env("VELAMESH_MIMO_TIMEOUT", "5") or 5)

    # Hub offline/degrade behaviour.
    HUB_OFFLINE_QUEUE_MAX: int = int(_env("VELAMESH_HUB_QUEUE_MAX", "5000") or 5000)
    HUB_NODE_OFFLINE_SECONDS: int = int(_env("VELAMESH_HUB_NODE_OFFLINE_SECONDS", "30") or 30)
    # Fusion thresholds (issue spec: normal 0.65, degraded 0.55).
    FUSION_THRESHOLD_NORMAL: float = float(_env("VELAMESH_FUSION_THRESHOLD", "0.65") or 0.65)
    FUSION_THRESHOLD_DEGRADED: float = float(_env("VELAMESH_FUSION_THRESHOLD_DEGRADED", "0.55") or 0.55)
    FUSION_FACE_DEGRADE_BELOW: float = float(_env("VELAMESH_FUSION_FACE_DEGRADE_BELOW", "0.3") or 0.3)

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
