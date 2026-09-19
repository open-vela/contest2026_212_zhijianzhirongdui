"""FastAPI application factory with lifespan, middleware, and router registration."""

import logging
from logging.handlers import RotatingFileHandler
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings

logging.basicConfig(
    level=logging.INFO if not settings.DEBUG else logging.DEBUG,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("app")


def _configure_file_logging() -> None:
    """Add a bounded local log file when a portable log directory is configured."""
    if not settings.LOG_DIR:
        return
    log_dir = Path(settings.LOG_DIR).expanduser()
    log_dir.mkdir(parents=True, exist_ok=True)
    # Legacy log file name kept for back-compat with existing deployments.
    log_file = (log_dir / "dominiscius.log").resolve()
    root_logger = logging.getLogger()
    if any(getattr(handler, "baseFilename", None) == str(log_file) for handler in root_logger.handlers):
        return
    handler = RotatingFileHandler(log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s"))
    root_logger.addHandler(handler)


_configure_file_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: init DB, connect MQTT on startup; cleanup on shutdown."""
    logger.info(f"{settings.APP_NAME} v{settings.APP_VERSION} starting...")

    # Initialize database (create tables + seed)
    from app.models.database import init_db
    await init_db()
    logger.info("Database initialized")

    # Start MQTT client
    from app.services.mqtt_client import mqtt_client
    from app.services.ws_manager import ws_manager
    from app.services.identity_engine import identity_engine
    from app.services.demo_telemetry import demo_telemetry
    from app.services.cloud_outbox import cloud_outbox
    from app.services.gait_adapter import gait_adapter

    # The cloud worker is deliberately independent of MQTT. Disabled or
    # unreachable cloud delivery must never stop the local demo from starting.
    await cloud_outbox.start()

    mqtt_client.start()

    # Wire up MQTT → Identity Engine (face / silhouette / ble / status)
    mqtt_client.subscribe(
        f"{settings.MQTT_TOPIC_PREFIX}/node/+/face",
        identity_engine.on_face,
    )
    mqtt_client.subscribe(
        f"{settings.MQTT_TOPIC_PREFIX}/node/+/silhouette",
        identity_engine.on_silhouette,
    )
    mqtt_client.subscribe(
        f"{settings.MQTT_TOPIC_PREFIX}/node/+/ble",
        identity_engine.on_ble,
    )
    mqtt_client.subscribe(
        f"{settings.MQTT_TOPIC_PREFIX}/node/+/status",
        identity_engine.on_status,
    )
    # Independent compact evidence path for the competition demo. This does
    # not replace the identity handlers above; it records every node channel
    # and exposes only summary fields to the UI.
    mqtt_client.subscribe(
        f"{settings.MQTT_TOPIC_PREFIX}/node/+/+",
        demo_telemetry.on_message,
    )
    # OPE-73 gait protocol adapter. The ESP32 publishes recognition results on
    # the ``dominiscius/+/gait/result`` topic (a different root from
    # ``vela/node/+/+``). The adapter normalizes them into the unified
    # ``gait_result`` event for the demo UI. The ESP32 topic is NOT modified.
    mqtt_client.subscribe(
        gait_adapter.topic_pattern,
        gait_adapter.on_message,
    )

    logger.info(f"MQTT client connected to {settings.MQTT_BROKER}:{settings.MQTT_PORT}")
    logger.info(f"{settings.APP_NAME} v{settings.APP_VERSION} started on {settings.HOST}:{settings.PORT}")

    yield

    # Shutdown
    mqtt_client.stop()
    await cloud_outbox.stop()
    logger.info("Application shutdown complete")


def _mount_spa(app: FastAPI, static_dir: Path) -> None:
    """Serve a Vite build without allowing the SPA fallback to mask missing assets."""
    static_dir = static_dir.expanduser().resolve()
    index_file = static_dir / "index.html"
    if not index_file.is_file():
        logger.warning("SPA index not found in %s", static_dir)
        return

    assets_dir = static_dir / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="spa-assets")
    legacy_static_dir = static_dir / "static"
    if legacy_static_dir.is_dir():
        app.mount("/static", StaticFiles(directory=str(legacy_static_dir)), name="spa-static")

    reserved = {"api", "ws", "health", "docs", "redoc", "openapi.json", "assets", "static"}

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        first_segment = full_path.split("/", 1)[0]
        if first_segment in reserved:
            raise HTTPException(status_code=404, detail="Not Found")

        candidate = (static_dir / full_path).resolve()
        if candidate.is_relative_to(static_dir) and candidate.is_file():
            return FileResponse(candidate)

        # A path with a suffix is a missing resource, not a Vue history route.
        if Path(full_path).suffix:
            raise HTTPException(status_code=404, detail="Static resource not found")
        return FileResponse(index_file)


def create_app(static_dir: str | Path | None = None) -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register routers (API routes first, before static catch-all)
    from app.api.auth import router as auth_router
    from app.api.persons import router as persons_router
    from app.api.visitors import router as visitors_router
    from app.api.devices import router as devices_router
    from app.api.spaces import router as spaces_router
    from app.api.events import router as events_router
    from app.api.events import recognition_router
    from app.api.audit import router as audit_router
    from app.api.rules import router as rules_router
    from app.api.energy import router as energy_router
    from app.api.users import user_router, role_router, perm_router
    from app.api.websocket_events import router as ws_router
    from app.api.inference import router as inference_router
    from app.api.dashboard import router as dashboard_router
    from app.api.demo import cloud_router, router as demo_router, ws_router as demo_ws_router

    app.include_router(auth_router)
    app.include_router(persons_router)
    app.include_router(visitors_router)
    app.include_router(devices_router)
    app.include_router(spaces_router)
    app.include_router(events_router)
    app.include_router(recognition_router)
    app.include_router(audit_router)
    app.include_router(rules_router)
    app.include_router(energy_router)
    app.include_router(user_router)
    app.include_router(role_router)
    app.include_router(perm_router)
    app.include_router(ws_router)
    app.include_router(inference_router)
    app.include_router(dashboard_router)
    app.include_router(demo_router)
    app.include_router(cloud_router)
    app.include_router(demo_ws_router)

    # Health check
    @app.get("/health")
    async def health():
        return {"status": "ok", "version": settings.APP_VERSION}

    resolved_static_dir = Path(static_dir) if static_dir is not None else Path(settings.STATIC_DIR)
    _mount_spa(app, resolved_static_dir)
    logger.info("SPA assets mounted from %s", resolved_static_dir)

    return app
