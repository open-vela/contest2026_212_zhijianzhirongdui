"""OPE-86 software-only integration tests for packaging, cloud, metrics and WS."""

from __future__ import annotations

import asyncio
import re
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select, update

from app.main import create_app
from app.models.database import async_session_factory, init_db
from app.models.models import CloudTransferAttempt, CloudTransferEvent, DemoMetricSnapshot
from app.services.auth_service import create_access_token
from app.services.cloud_outbox import CloudOutboxWorker
from app.services.cloud_transport import (
    DeliveryResult,
    DisabledCloudTransport,
    HttpCloudTransport,
    MisconfiguredHttpCloudTransport,
)
from app.services.demo_metrics import demo_metrics
from app.services.demo_telemetry import demo_telemetry


ROOT = Path(__file__).resolve().parents[2]
CLIENT_DIST = ROOT / "client" / "dist"
API_APP = create_app(static_dir=CLIENT_DIST if CLIENT_DIST.exists() else ROOT / "server" / "static")


@pytest.fixture(autouse=True)
async def _database_ready():
    await init_db()
    yield


async def _token() -> str:
    transport = ASGITransport(app=API_APP)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/auth/login", json={
            "username": "admin",
            "password": "admin123",
            "tenant_code": "default",
        })
    assert response.status_code == 200
    return response.json()["access_token"]


async def _post(path: str, body: dict):
    token = await _token()
    transport = ASGITransport(app=API_APP)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post(path, json=body, headers={"Authorization": f"Bearer {token}"})


async def test_vite_production_assets_and_history_fallback():
    if not (CLIENT_DIST / "index.html").exists():
        pytest.skip("Run `npm run build` before the production asset integration test")
    app = create_app(static_dir=CLIENT_DIST)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        page = await client.get("/admin/demo")
        refresh = await client.get("/admin/demo/")
        favicon = await client.get("/favicon.svg")
        api = await client.get("/health")
        missing_api = await client.get("/api/not-a-real-route")
        missing_asset = await client.get("/assets/not-a-real-file.js")
        missing_root_resource = await client.get("/not-a-real-file.js")

        assert page.status_code == refresh.status_code == 200
        assert "text/html" in page.headers["content-type"]
        assert page.text == refresh.text
        assert favicon.status_code == 200
        assert "image/svg+xml" in favicon.headers["content-type"]
        assert api.status_code == 200 and api.json()["status"] == "ok"
        assert missing_api.status_code == missing_asset.status_code == missing_root_resource.status_code == 404

        script_path = re.search(r'src="(/assets/[^"]+\.js)"', page.text)
        style_path = re.search(r'href="(/assets/[^"]+\.css)"', page.text)
        assert script_path and style_path
        script = await client.get(script_path.group(1))
        style = await client.get(style_path.group(1))
        assert script.status_code == style.status_code == 200
        assert "javascript" in script.headers["content-type"]
        assert "text/css" in style.headers["content-type"]


async def test_cloud_upload_and_receive_are_idempotent():
    key = f"upload-{uuid.uuid4().hex}"
    body = {"event_type": "idempotency_test", "payload": {"value": 1}, "idempotency_key": key}
    first = await _post("/api/cloud/upload", body)
    second = await _post("/api/cloud/upload", body)
    assert first.status_code == second.status_code == 202
    assert first.json()["data"]["request_id"] == second.json()["data"]["request_id"]
    assert first.json()["data"]["duplicate"] is False
    assert second.json()["data"]["duplicate"] is True

    # Upload and receive directions may use the same key (a common cloud ACK
    # contract), while each direction remains independently idempotent.
    receive_key = key
    receive = {"event_type": "receiver_event", "payload": {"accepted": True}, "idempotency_key": receive_key, "provider": "test_http"}
    inbound_first = await _post("/api/cloud/receive", receive)
    inbound_second = await _post("/api/cloud/receive", receive)
    assert inbound_first.status_code == inbound_second.status_code == 202
    assert inbound_first.json()["data"]["request_id"] == inbound_second.json()["data"]["request_id"]
    assert inbound_second.json()["data"]["duplicate"] is True
    assert inbound_first.json()["data"]["provenance"] in {"mock", "pending_real"}


class SequenceTransport:
    mode = "mock"
    provider = "test_mock"

    def __init__(self, results: list[DeliveryResult]):
        self.results = results

    async def deliver(self, envelope: dict) -> DeliveryResult:
        assert envelope["idempotency_key"]
        return self.results.pop(0)


class RaisingTransport:
    mode = "http"
    provider = "raising_test"

    async def deliver(self, envelope: dict) -> DeliveryResult:
        raise RuntimeError("adapter exploded")


async def _new_outbox_event(*, status: str = "pending", max_retries: int = 3) -> int:
    async with async_session_factory() as db:
        event = CloudTransferEvent(
            tenant_id=1,
            request_id=uuid.uuid4().hex,
            idempotency_key=uuid.uuid4().hex,
            direction="upload",
            event_type="worker_test",
            status=status,
            payload_json={"hello": "world"},
            provider="test_mock",
            transport="mock",
            provenance="mock",
            max_retries=max_retries,
            next_attempt_at=datetime.utcnow(),
        )
        db.add(event)
        await db.commit()
        return event.id


async def test_cloud_worker_retry_delivery_receipt_and_restart_recovery():
    async with async_session_factory() as db:
        await db.execute(delete(CloudTransferAttempt))
        await db.execute(delete(CloudTransferEvent))
        await db.commit()

    transport = SequenceTransport([
        DeliveryResult(False, error_code="TEST_DOWN", error_message="temporary"),
        DeliveryResult(True, status_code=202, receipt={"accepted": True}),
    ])
    worker = CloudOutboxWorker(transport)
    event_id = await _new_outbox_event()
    assert await worker.process_once() == 1
    async with async_session_factory() as db:
        retrying = await db.get(CloudTransferEvent, event_id)
        assert retrying.status == "retrying"
        assert retrying.retry_count == 1
        assert retrying.error_code == "TEST_DOWN"
        await db.execute(update(CloudTransferEvent).where(CloudTransferEvent.id == event_id).values(next_attempt_at=datetime.utcnow()))
        await db.commit()

    assert await worker.process_once() == 1
    async with async_session_factory() as db:
        delivered = await db.get(CloudTransferEvent, event_id)
        receipts = (await db.execute(select(CloudTransferEvent).where(CloudTransferEvent.direction == "receive"))).scalars().all()
        attempts = (await db.execute(
            select(CloudTransferAttempt).where(CloudTransferAttempt.transfer_id == event_id).order_by(CloudTransferAttempt.attempt_number)
        )).scalars().all()
        assert delivered.status == "delivered"
        assert delivered.retry_count == 1
        assert delivered.provenance == "mock"
        assert delivered.receipt_json["accepted"] is True
        assert len(receipts) == 1 and receipts[0].status == "delivered"
        assert [attempt.status for attempt in attempts] == ["failed", "delivered"]

    stale_id = await _new_outbox_event(status="sending")
    assert await worker.recover_stale() == 1
    async with async_session_factory() as db:
        stale = await db.get(CloudTransferEvent, stale_id)
        assert stale.status == "retrying"
        assert stale.error_code == "WORKER_RESTART"


async def test_cloud_worker_stops_at_max_retries():
    async with async_session_factory() as db:
        await db.execute(delete(CloudTransferAttempt))
        await db.execute(delete(CloudTransferEvent))
        await db.commit()
    worker = CloudOutboxWorker(SequenceTransport([
        DeliveryResult(False, error_code="DOWN", error_message="first"),
        DeliveryResult(False, error_code="DOWN", error_message="second"),
    ]))
    event_id = await _new_outbox_event(max_retries=2)
    await worker.process_once()
    async with async_session_factory() as db:
        await db.execute(update(CloudTransferEvent).where(CloudTransferEvent.id == event_id).values(next_attempt_at=datetime.utcnow()))
        await db.commit()
    await worker.process_once()
    async with async_session_factory() as db:
        event = await db.get(CloudTransferEvent, event_id)
        attempts = (await db.execute(select(CloudTransferAttempt).where(CloudTransferAttempt.transfer_id == event_id))).scalars().all()
        assert event.status == "failed"
        assert event.retry_count == 2
        assert event.next_attempt_at is None
        assert len(attempts) == 2


async def test_cloud_worker_contains_adapter_exceptions_and_disabled_mode():
    async with async_session_factory() as db:
        await db.execute(delete(CloudTransferAttempt))
        await db.execute(delete(CloudTransferEvent))
        await db.commit()
    event_id = await _new_outbox_event(max_retries=2)
    worker = CloudOutboxWorker(RaisingTransport())
    assert await worker.process_once() == 1
    async with async_session_factory() as db:
        event = await db.get(CloudTransferEvent, event_id)
        assert event.status == "retrying"
        assert event.error_code == "TRANSPORT_EXCEPTION"

    disabled = CloudOutboxWorker(DisabledCloudTransport())
    await disabled.start()
    assert disabled.is_running is False
    await disabled.stop()

    misconfigured = await MisconfiguredHttpCloudTransport().deliver({})
    assert misconfigured.delivered is False
    assert misconfigured.error_code == "HTTP_ENDPOINT_MISSING"


async def test_http_transport_success_and_failure_endpoint():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Idempotency-Key"] == "http-test-key"
        if request.url.path == "/ok":
            return httpx.Response(202, json={"accepted": True})
        return httpx.Response(503, json={"error": "unavailable"})

    mock_network = httpx.MockTransport(handler)
    envelope = {
        "request_id": "request",
        "idempotency_key": "http-test-key",
        "event_type": "test",
        "payload": {},
        "created_at": datetime.utcnow().isoformat() + "Z",
    }
    success = await HttpCloudTransport("https://example.test/ok", 1, transport=mock_network).deliver(envelope)
    failure = await HttpCloudTransport("https://example.test/fail", 1, transport=mock_network).deliver(envelope)
    assert success.delivered is True and success.status_code == 202
    assert failure.delivered is False and failure.error_code == "HTTP_503"

    def timeout_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    timeout = await HttpCloudTransport(
        "https://example.test/timeout", 0.01, transport=httpx.MockTransport(timeout_handler)
    ).deliver(envelope)
    assert timeout.delivered is False and timeout.error_code == "HTTP_TIMEOUT"


async def test_metrics_calculation_mock_provenance_and_restart_restore():
    demo_telemetry.clear()
    demo_metrics.clear()
    async with async_session_factory() as db:
        await db.execute(delete(DemoMetricSnapshot))
        await db.commit()

    prefix = f"metric-{uuid.uuid4().hex[:8]}"
    await demo_telemetry.ingest(
        f"vela/node/{prefix}/metrics",
        {
            "node_id": prefix,
            "metrics": {
                "discovery_started_at": (datetime.utcnow() - timedelta(milliseconds=400)).isoformat() + "Z",
                "discovered_at": datetime.utcnow().isoformat() + "Z",
                "connection_ms": 780,
                "sent_count": 1000,
                "received_count": 995,
                "sync_skew_ms": 35,
                "modality_count": 3,
            },
        },
        provenance="mock",
        persist=True,
    )
    await demo_telemetry.ingest(
        f"vela/node/{prefix}/service",
        {
            "node_id": prefix,
            "service_owner": prefix,
            "active_node": prefix,
            "backup_node": f"{prefix}-backup",
            "service_switch_ms": 520,
            "interruption_ms": 110,
        },
        provenance="mock",
        persist=True,
    )
    async with async_session_factory() as db:
        items = {item["key"]: item for item in await demo_metrics.metric_items(db, 1)}
    assert items["messages_sent"]["value"] == 1000
    assert items["messages_received"]["value"] == 995
    assert items["reliability"]["value"] == 99.5
    assert items["packet_loss"]["value"] == 0.5
    assert items["service_owner"]["value"] == prefix
    assert items["service_migration"]["value"] is True
    assert items["service_switch"]["provenance"] == "mock"

    demo_metrics.clear()
    async with async_session_factory() as db:
        restored = {item["key"]: item for item in await demo_metrics.metric_items(db, 1)}
    assert restored["reliability"]["value"] == 99.5
    assert restored["service_owner"]["value"] == prefix
    assert restored["service_owner"]["provenance"] == "mock"


async def test_metrics_derive_reconnect_latency_and_multi_node_sync():
    demo_telemetry.clear()
    demo_metrics.clear()
    base = datetime.utcnow()
    await demo_telemetry.ingest(
        "vela/node/derive-a/status",
        {"node_id": "derive-a", "mqtt_connected": False, "ts": (base - timedelta(milliseconds=40)).isoformat() + "Z"},
        persist=False,
        provenance="real",
    )
    await asyncio.sleep(0.01)
    await demo_telemetry.ingest(
        "vela/node/derive-a/status",
        {"node_id": "derive-a", "mqtt_connected": True, "ts": base.isoformat() + "Z"},
        persist=False,
        provenance="real",
    )
    await demo_telemetry.ingest(
        "vela/node/derive-b/status",
        {"node_id": "derive-b", "mqtt_connected": True, "ts": (base + timedelta(milliseconds=18)).isoformat() + "Z"},
        persist=False,
        provenance="real",
    )
    async with async_session_factory() as db:
        items = {item["key"]: item for item in await demo_metrics.metric_items(db, 1)}
    assert items["reconnect"]["value"] >= 0
    assert items["interruption"]["value"] == items["reconnect"]["value"]
    assert items["multi_device_sync"]["value"] == 18
    assert items["end_to_end"]["value"] is not None
    assert items["reconnect"]["provenance"] == "real"


def test_demo_websocket_authenticated_snapshot():
    token = create_access_token({"sub": "1"})
    with TestClient(API_APP) as client:
        with client.websocket_connect(f"/ws/demo-events?token={token}") as websocket:
            message = websocket.receive_json()
            assert message["type"] == "snapshot"
            assert isinstance(message["data"], list)


def test_gait_adapter_transform_maps_payload_to_unified_event():
    from app.services.gait_adapter import gait_adapter

    event = gait_adapter.transform("dominiscius/idf-gait-01/gait/result", {
        "session_id": "sess-1",
        "direction": "forward",
        "top3": [
            {"identity": "Alice", "score": 0.8721},
            {"identity": "Bob", "score": 0.7289},
        ],
        "cosine": 0.8721,
        "margin": 0.1432,
        "timing": {"total_ms": 128},
    })
    payload = event["payload"]
    assert event["node_id"] == "idf-gait-01"
    assert payload["identity"] == "Alice"
    assert payload["score"] == 0.8721
    assert payload["direction"] == "forward"
    assert payload["source"] == "gait"
    assert payload["session_id"] == "sess-1"
    assert payload["latency"] == 128.0
    assert payload["cosine"] == 0.8721
    assert payload["margin"] == 0.1432
    assert payload["top3"] == [
        {"identity": "Alice", "score": 0.8721},
        {"identity": "Bob", "score": 0.7289},
    ]


def test_gait_adapter_transform_falls_back_to_cosine_and_scalar_timing():
    from app.services.gait_adapter import gait_adapter

    # top3 entry has no score -> fall back to top-level cosine;
    # timing is a scalar -> interpreted as ms; node_id comes from the topic.
    event = gait_adapter.transform("dominiscius/node-x/gait/result", {
        "session_id": "s2",
        "direction": "back",
        "top3": [{"identity": "Carol"}],
        "cosine": 0.55,
        "margin": 0.05,
        "timing": 99,
    })
    payload = event["payload"]
    assert event["node_id"] == "node-x"
    assert payload["identity"] == "Carol"
    assert payload["score"] == 0.55
    assert payload["latency"] == 99.0
    assert payload["top3"] == [{"identity": "Carol", "score": None}]


async def test_gait_adapter_persists_and_reaches_rest_endpoint():
    from app.services.gait_adapter import gait_adapter

    demo_telemetry.clear()
    await gait_adapter.on_message("dominiscius/idf-gait-01/gait/result", {
        "session_id": "sess-e2e",
        "direction": "forward",
        "top3": [{"identity": "Alice", "score": 0.88}, {"identity": "Bob", "score": 0.6}],
        "cosine": 0.88,
        "margin": 0.1,
        "timing": {"total_ms": 77},
    })

    token = await _token()
    transport = ASGITransport(app=API_APP)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/demo/ope73/gait", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["node_id"] == "idf-gait-01"
    assert data["identity"] == "Alice"
    assert data["score"] == 0.88
    assert data["direction"] == "forward"
    assert data["source"] == "gait"
    assert data["session_id"] == "sess-e2e"
    assert data["latency"] == 77.0
    assert data["cosine"] == 0.88
    assert data["margin"] == 0.1
    assert len(data["top3"]) == 2
    assert data["top3"][0] == {"identity": "Alice", "score": 0.88}
    assert data["provenance"] == "real"
    assert data["server_receive"]["last_topic"] == "dominiscius/idf-gait-01/gait/result"


async def test_gait_adapter_publishes_unified_event_on_demo_bus():
    from app.services.demo_event_bus import demo_event_bus
    from app.services.gait_adapter import gait_adapter

    demo_telemetry.clear()
    queue = demo_event_bus.subscribe()
    try:
        await gait_adapter.on_message("dominiscius/idf-gait-01/gait/result", {
            "session_id": "sess-bus",
            "direction": "forward",
            "top3": [{"identity": "Dave", "score": 0.71}],
            "cosine": 0.71,
            "margin": 0.03,
            "timing": {"total_ms": 55},
        })
        # ingest() also fans out a "telemetry" event; we only care that the
        # spec-compliant "gait_result" event was published.
        events = []
        while not queue.empty():
            events.append(queue.get_nowait())
        event_types = [event["type"] for event in events]
        assert "gait_result" in event_types
        gait_event = next(event for event in events if event["type"] == "gait_result")
        assert gait_event["data"]["identity"] == "Dave"
        assert gait_event["data"]["source"] == "gait"
        assert gait_event["data"]["session_id"] == "sess-bus"
        assert gait_event["data"]["latency"] == 55.0
        assert gait_event["tenant_id"] == 1
    finally:
        demo_event_bus.unsubscribe(queue)
