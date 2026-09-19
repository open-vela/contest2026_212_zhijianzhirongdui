"""Static acceptance tests for the portable two-container demo bundle."""

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
DEPLOY = ROOT / "deploy" / "demo"


def test_compose_parses_and_has_portable_services():
    manifest = yaml.safe_load((DEPLOY / "docker-compose.yml").read_text(encoding="utf-8"))
    assert set(manifest["services"]) == {"app", "mqtt"}
    app = manifest["services"]["app"]
    mqtt = manifest["services"]["mqtt"]
    assert app["depends_on"]["mqtt"]["condition"] == "service_healthy"
    assert app["pull_policy"] == mqtt["pull_policy"] == "never"
    assert "healthcheck" in app and "healthcheck" in mqtt
    assert "./data/app:/app/server/data" in app["volumes"]
    assert "./logs/app:/app/server/logs" in app["volumes"]
    assert "./data/mqtt:/mosquitto/data" in mqtt["volumes"]
    assert "./logs/mqtt:/mosquitto/log" in mqtt["volumes"]
    assert "volumes" not in manifest  # no non-portable named volumes


def test_dockerfile_is_multistage_and_embeds_vue_build():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "FROM node:20-alpine AS web-builder" in dockerfile
    assert "FROM python:3.11-slim AS runtime" in dockerfile
    assert "npm run build" in dockerfile
    assert "COPY --from=web-builder" in dockerfile
    assert '"--workers", "1"' in dockerfile


def test_venue_start_and_stop_scripts_do_not_install_or_destroy_data():
    start = (DEPLOY / "scripts" / "start-demo.cmd").read_text(encoding="utf-8").lower()
    stop = (DEPLOY / "scripts" / "stop-demo.cmd").read_text(encoding="utf-8").lower()
    for forbidden in ("npm install", "npm ci", "pip install", "docker pull", "compose build"):
        assert forbidden not in start
    assert "--no-build" in start
    assert 'docker image inspect "eclipse-mosquitto:2.0.20"' in start
    assert "down -v" not in stop and "--volumes" not in stop


def test_portable_bundle_has_all_windows_operations():
    required = {
        "start-demo.cmd", "stop-demo.cmd", "status-demo.cmd", "smoke-test.cmd",
        "backup-data.cmd", "restore-data.cmd", "import-images.cmd", "export-images.cmd",
    }
    scripts = {path.name for path in (DEPLOY / "scripts").iterdir() if path.is_file()}
    assert required.issubset(scripts)
    assert (DEPLOY / ".env.example").is_file()
    assert (DEPLOY / "VERSION.txt").is_file()
