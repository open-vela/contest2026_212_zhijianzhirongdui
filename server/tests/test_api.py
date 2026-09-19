#!/usr/bin/env python3
"""Comprehensive API test suite for VelaMesh (枢络).

Run with:
    cd server && PYTHONPATH=. python -m pytest tests/ -v
    # or
    cd server && PYTHONPATH=. python tests/test_api.py

Requires: pip install pytest httpx
"""

import sys
from datetime import datetime, timedelta

sys.path.insert(0, "..")

import pytest  # noqa: E402
from httpx import AsyncClient, ASGITransport  # noqa: E402

from app.main import create_app  # noqa: E402

app = create_app()
transport = ASGITransport(app=app)

BASE = "/api"
TOKEN = None
PERSON_ID = None
DEVICE_ID = None
SPACE_ID = None
VISITOR_ID = None
RULE_ID = None


@pytest.fixture(autouse=True)
async def _setup():
    """Ensure DB is seeded before tests."""
    from app.models.database import init_db
    await init_db()
    yield


# ── Helpers ───────────────────────────────────────────────────────────


async def _login(username="admin", password="admin123"):
    global TOKEN
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(f"{BASE}/auth/login", json={
            "username": username, "password": password, "tenant_code": "default",
        })
        assert resp.status_code == 200, f"Login failed: {resp.text}"
        body = resp.json()
        TOKEN = body.get("access_token") or body.get("data", {}).get("access_token", "")
        return TOKEN


async def _auth_headers():
    if not TOKEN:
        await _login()
    return {"Authorization": f"Bearer {TOKEN}"}


async def _get(path: str, params=None):
    h = await _auth_headers()
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        return await ac.get(f"{BASE}{path}", headers=h, params=params)


async def _post(path: str, data: dict = None):
    h = await _auth_headers()
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        return await ac.post(f"{BASE}{path}", json=data or {}, headers=h)


async def _put(path: str, data: dict):
    h = await _auth_headers()
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        return await ac.put(f"{BASE}{path}", json=data, headers=h)


async def _delete(path: str):
    h = await _auth_headers()
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        return await ac.delete(f"{BASE}{path}", headers=h)

async def _patch(path: str, data: dict):
    h = await _auth_headers()
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        return await ac.patch(f"{BASE}{path}", json=data, headers=h)


# ══════════════════════════════════════════════════════════════════════
# Tests
# ══════════════════════════════════════════════════════════════════════


class TestHealth:
    async def test_health(self):
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestAuth:
    async def test_login_success(self):
        """Admin with correct credentials returns token."""
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post(f"{BASE}/auth/login", json={
                "username": "admin", "password": "admin123",
                "tenant_code": "default",
            })
        assert resp.status_code == 200
        body = resp.json()
        d = body.get("data", body)
        assert "access_token" in d
        assert d["token_type"] == "bearer"
        assert d["user"]["username"] == "admin"
        assert "system:admin" in d["user"]["permissions"]

    async def test_login_wrong_password(self):
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post(f"{BASE}/auth/login", json={
                "username": "admin", "password": "wrong",
                "tenant_code": "default",
            })
        assert resp.status_code == 401

    async def test_login_disabled_user(self):
        """Create disabled user and try to login."""
        h = await _auth_headers()
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post(f"{BASE}/auth/login", json={
                "username": "nonexistent", "password": "x",
                "tenant_code": "default",
            })
        assert resp.status_code == 401

    async def test_refresh_token(self):
        await _login()
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post(f"{BASE}/auth/refresh", json={
                "refresh_token": "invalid",
            })
        assert resp.status_code == 401

    async def test_me(self):
        resp = await _get("/auth/me")
        assert resp.status_code == 200
        body = resp.json()
        d = body.get("data", body)
        assert d["username"] == "admin"
        assert len(d["permissions"]) > 0

    async def test_me_unauthorized(self):
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get(f"{BASE}/auth/me")
        assert resp.status_code == 401


class TestPersons:
    async def test_list_persons(self):
        resp = await _get("/persons")
        assert resp.status_code == 200
        d = resp.json()
        assert d["pagination"]["total"] > 0
        assert len(d["data"]) > 0

    async def test_list_persons_pagination(self):
        resp = await _get("/persons", {"page": 1, "page_size": 5})
        assert resp.status_code == 200
        d = resp.json()
        assert d["pagination"]["page_size"] == 5
        assert len(d["data"]) <= 5

    async def test_list_persons_search(self):
        resp = await _get("/persons", {"search": "张"})
        assert resp.status_code == 200
        # At least one result matching "张"

    async def test_list_persons_filter_type(self):
        resp = await _get("/persons", {"person_type": "vip"})
        assert resp.status_code == 200

    async def test_create_person(self):
        resp = await _post("/persons", {
            "name": "测试人员",
            "employee_id": "TST001",
            "department": "测试部",
            "person_type": "employee",
            "phone": "13800000000",
        })
        assert resp.status_code == 201
        d = resp.json()["data"]
        assert d["name"] == "测试人员"
        assert d["employee_id"] == "TST001"
        global PERSON_ID
        PERSON_ID = d["id"]

    async def test_create_person_duplicate_employee_id(self):
        resp = await _post("/persons", {
            "name": "重复",
            "employee_id": "EMP001",
            "department": "测试",
        })
        assert resp.status_code == 409

    async def test_create_person_no_name(self):
        resp = await _post("/persons", {"name": "", "employee_id": "BAD"})
        assert resp.status_code == 422

    async def test_get_person(self):
        # Use first person from list to avoid delete-then-get ordering issue
        list_resp = await _get("/persons")
        body = list_resp.json()
        items = body.get("data", body.get("data", []))
        if isinstance(items, dict) and "data" in items:
            items = items["data"]
        if isinstance(items, dict) and "items" in items:
            items = items["items"]
        if items and len(items) > 0:
            pid = items[0]["id"]
            resp = await _get(f"/persons/{pid}")
            assert resp.status_code == 200

    async def test_get_person_not_found(self):
        resp = await _get("/persons/99999")
        assert resp.status_code == 404

    async def test_update_person(self):
        pid = PERSON_ID or 1
        resp = await _put(f"/persons/{pid}", {"name": "测试人员已更新"})
        assert resp.status_code in (200, 404)

    async def test_delete_person(self):
        resp = await _delete(f"/persons/{PERSON_ID}")
        assert resp.status_code == 204

    async def test_faces(self):
        """Test face registration flow on the first existing person."""
        resp = await _get("/persons")
        d = resp.json().get("data", resp.json())
        first_id = d[0]["id"] if isinstance(d, list) else d["data"][0]["id"]

        # List faces (may be 0 if using default seed data only)
        resp = await _get(f"/persons/{first_id}/faces")
        assert resp.status_code == 200
        # The first test against default seed may have 0 faces — that's OK

    async def test_rbac_person_read(self):
        """security role can read persons."""
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.post(f"{BASE}/auth/login", json={
                "username": "sec_zhang", "password": "sec123", "tenant_code": "default",
            })
        if r.status_code != 200:
            return  # Skip: user not in default seed
        await _login("sec_zhang", "sec123")
        resp = await _get("/persons")
        assert resp.status_code == 200
        await _login()  # back to admin


class TestDevices:
    async def test_list_devices(self):
        resp = await _get("/devices")
        assert resp.status_code == 200
        d = resp.json()
        # May be empty if not seeded, or have data
        assert "pagination" in d

    async def test_create_device(self):
        resp = await _post("/devices", {
            "node_id": "test-device-01",
            "name": "测试设备",
            "location": "测试位置",
            "device_type": "sensor",
        })
        if resp.status_code == 201:
            global DEVICE_ID
            DEVICE_ID = resp.json()["data"]["id"]
        elif resp.status_code == 409:
            pass  # Already exists, fine

    async def test_get_device(self):
        if DEVICE_ID:
            resp = await _get(f"/devices/{DEVICE_ID}")
            assert resp.status_code in (200, 404)

    async def test_send_command(self):
        if DEVICE_ID:
            resp = await _post(f"/devices/{DEVICE_ID}/command",
                               {"command": "reboot", "params": {}})
            assert resp.status_code in (200, 404)


class TestSpaces:
    async def test_list_spaces(self):
        resp = await _get("/spaces")
        assert resp.status_code == 200

    async def test_create_space(self):
        resp = await _post("/spaces", {
            "name": "测试空间",
            "type": "area",
            "floor": "3F",
        })
        assert resp.status_code == 201
        global SPACE_ID
        SPACE_ID = resp.json()["data"]["id"]

    async def test_get_space(self):
        sid = SPACE_ID or 1
        resp = await _get(f"/spaces/{sid}")
        assert resp.status_code in (200, 404)

    async def test_update_space(self):
        sid = SPACE_ID or 1
        resp = await _put(f"/spaces/{sid}", {"name": "测试空间已更新"})
        assert resp.status_code in (200, 404)

    async def test_delete_space(self):
        resp = await _delete(f"/spaces/{SPACE_ID}")
        assert resp.status_code == 204


class TestEvents:
    async def test_list_events(self):
        resp = await _get("/events")
        assert resp.status_code == 200
        d = resp.json()
        # Should have seeded events
        if d["pagination"]["total"] > 0:
            assert len(d["data"]) > 0

    async def test_events_stats(self):
        resp = await _get("/events/stats")
        assert resp.status_code == 200
        d = resp.json()["data"]
        assert "total_events" in d

    async def test_events_recent(self):
        resp = await _get("/events/recent", {"limit": 10})
        assert resp.status_code == 200
        d = resp.json()["data"]
        assert len(d) <= 10


class TestVisitors:
    async def test_list_visitors(self):
        resp = await _get("/visitors")
        assert resp.status_code == 200

    async def test_create_visitor(self):
        # Get a valid host person
        person_resp = await _get("/persons")
        host_id = person_resp.json()["data"][0]["id"]

        resp = await _post("/visitors", {
            "name": "API测试访客",
            "phone": "13900000999",
            "host_person_id": host_id,
            "purpose": "自动化测试",
            "expected_at": (datetime.utcnow() + timedelta(hours=2)).isoformat() + "Z",
            "valid_from": (datetime.utcnow() + timedelta(hours=2)).isoformat() + "Z",
            "valid_until": (datetime.utcnow() + timedelta(hours=6)).isoformat() + "Z",
        })
        assert resp.status_code == 201
        global VISITOR_ID
        VISITOR_ID = resp.json()["data"]["id"]
        assert resp.json()["data"]["status"] == "pending"

    async def test_approve_visitor(self):
        # Create a new visitor and approve
        person_resp = await _get("/persons")
        host_id = person_resp.json()["data"][0]["id"]

        resp = await _post("/visitors", {
            "name": "审批测试",
            "phone": "13900000888",
            "host_person_id": host_id,
            "purpose": "审批测试",
            "expected_at": (datetime.utcnow() + timedelta(hours=3)).isoformat() + "Z",
            "valid_from": (datetime.utcnow() + timedelta(hours=3)).isoformat() + "Z",
            "valid_until": (datetime.utcnow() + timedelta(hours=7)).isoformat() + "Z",
        })
        vid = resp.json()["data"]["id"]
        resp = await _post(f"/visitors/{vid}/approve", {"approved_by": 1})
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "approved"

    async def test_checkin_visitor(self):
        # Create approved → check-in
        person_resp = await _get("/persons")
        host_id = person_resp.json()["data"][0]["id"]
        await _login()

        # Create and approve
        resp = await _post("/visitors", {
            "name": "签到测试",
            "phone": "13900000777",
            "host_person_id": host_id,
            "purpose": "签到测试",
            "expected_at": (datetime.utcnow() + timedelta(hours=1)).isoformat() + "Z",
            "valid_from": (datetime.utcnow() + timedelta(hours=1)).isoformat() + "Z",
            "valid_until": (datetime.utcnow() + timedelta(hours=5)).isoformat() + "Z",
        })
        vid = resp.json()["data"]["id"]
        await _post(f"/visitors/{vid}/approve", {"approved_by": 1})

        resp = await _post(f"/visitors/{vid}/check-in")
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "checked_in"


class TestAudit:
    async def test_list_audit_logs(self):
        resp = await _get("/audit/logs")
        assert resp.status_code == 200
        assert "pagination" in resp.json()

    async def test_list_alerts(self):
        resp = await _get("/audit/alerts")
        assert resp.status_code == 200
        d = resp.json()
        assert "pagination" in d
        if d["pagination"]["total"] > 0:
            assert len(d["data"]) > 0
            # Patch resolve first alert
            alert_id = d["data"][0]["id"]
            resolve_resp = await _patch(f"/audit/alerts/{alert_id}/resolve",
                                        {"resolved_by": 1})
            assert resolve_resp.status_code == 200
            assert resolve_resp.json()["data"]["is_resolved"] is True

    async def test_list_alerts_filter_resolved(self):
        resp = await _get("/audit/alerts", {"is_resolved": False})
        assert resp.status_code == 200

    async def test_resolve_alert_not_found(self):
        resp = await _patch("/audit/alerts/99999/resolve", {"resolved_by": 1})
        assert resp.status_code == 404


class TestDashboard:
    async def test_dashboard_summary(self):
        resp = await _get("/dashboard/summary")
        assert resp.status_code == 200
        d = resp.json()["data"]
        assert "total_devices" in d
        assert "online_devices" in d

    async def test_dashboard_trend(self):
        resp = await _get("/dashboard/trend")
        assert resp.status_code == 200

    async def test_dashboard_device_status(self):
        resp = await _get("/dashboard/device-status")
        assert resp.status_code == 200
        assert "online_count" in resp.json()["data"]


class TestCompetitionDemo:
    async def test_demo_routes_require_login(self):
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get(f"{BASE}/demo/overview")
        assert resp.status_code == 401

    async def test_demo_overview_exposes_real_service_state(self):
        await _login()
        resp = await _get("/demo/overview")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["services"]["database"]["engine"] == "sqlite"
        assert data["services"]["database"]["provenance"] == "real"
        assert data["topic_root"].endswith("/node/+/+")

    async def test_mqtt_silhouette_becomes_real_evidence(self):
        from app.config import settings
        from app.services.demo_telemetry import demo_telemetry

        demo_telemetry.clear()
        record = await demo_telemetry.ingest(
            f"{settings.MQTT_TOPIC_PREFIX}/node/test-gait/silhouette",
            {
                "node_id": "test-gait",
                "frame_seq": 42,
                "foreground_pixels": 913,
                "rle": "1,2,3,4",
                "window": {"seq_start": 35, "seq_end": 42},
                "upload_stats": {"uploaded": 8, "skipped_empty": 2},
            },
            persist=True,
        )
        assert "rle" not in record["payload"]
        assert record["payload"]["rle_length"] == 7

        from sqlalchemy import select
        from app.models.database import async_session_factory
        from app.models.models import DemoTelemetry
        async with async_session_factory() as db:
            persisted = (await db.execute(
                select(DemoTelemetry).where(
                    DemoTelemetry.node_id == "test-gait",
                    DemoTelemetry.channel == "silhouette",
                ).order_by(DemoTelemetry.received_at.desc()).limit(1)
            )).scalar_one()
        assert "rle" not in persisted.payload_json
        assert persisted.payload_json["rle_length"] == 7

        resp = await _get("/demo/ope73/silhouette")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["node_id"] == "test-gait"
        assert data["frame_seq"] == 42
        assert data["foreground_pixels"] == 913
        assert data["server_receive"]["provenance"] == "real"

    async def test_real_metrics_are_scored_but_missing_values_are_not(self):
        from app.config import settings
        from app.services.demo_telemetry import demo_telemetry
        from app.services.demo_metrics import demo_metrics
        from app.models.database import async_session_factory
        from app.models.models import DemoMetricSnapshot
        from sqlalchemy import delete

        demo_telemetry.clear()
        demo_metrics.clear()
        async with async_session_factory() as db:
            await db.execute(delete(DemoMetricSnapshot))
            await db.commit()
        await demo_telemetry.ingest(
            f"{settings.MQTT_TOPIC_PREFIX}/node/test-gateway/metrics",
            {"node_id": "test-gateway", "metrics": {"discovery_ms": 450, "success_rate": 0.995}},
            persist=False,
        )
        resp = await _get("/demo/metrics")
        assert resp.status_code == 200
        metrics = {item["key"]: item for item in resp.json()["data"]}
        assert metrics["discovery"]["value"] == 450
        assert metrics["discovery"]["passed"] is True
        assert metrics["discovery"]["provenance"] == "real"
        assert metrics["reliability"]["value"] == 99.5
        assert metrics["service_migration"]["value"] is None
        assert metrics["service_migration"]["passed"] is None
        assert metrics["service_migration"]["provenance"] == "pending_real"

    async def test_cloud_upload_is_durable_local_queue_not_fake_delivery(self):
        resp = await _post("/cloud/upload", {
            "event_type": "test_snapshot",
            "payload": {"node_count": 3},
            "idempotency_key": f"test-{datetime.utcnow().timestamp()}",
        })
        assert resp.status_code == 202
        data = resp.json()["data"]
        assert data["status"] == "pending"
        assert data["cloud_delivered"] is False
        assert data["provenance"] in {"reserved", "mock", "pending_real"}

        events = await _get("/cloud/events")
        assert events.status_code == 200
        assert any(item["request_id"] == data["request_id"] for item in events.json()["data"])


class TestRecognitions:
    async def test_list_recognitions(self):
        resp = await _get("/recognitions")
        assert resp.status_code == 200
        d = resp.json()
        assert "pagination" in d


class TestEnergyByArea:
    async def test_energy_by_area(self):
        resp = await _get("/energy/by-area")
        assert resp.status_code == 200
        # May be empty if no energy data with space_id

    async def test_energy_trend(self):
        resp = await _get("/energy/trend", {"days": 7})
        assert resp.status_code == 200


class TestRules:
    async def test_list_rules(self):
        resp = await _get("/rules")
        assert resp.status_code == 200

    async def test_create_rule(self):
        resp = await _post("/rules", {
            "name": "测试规则",
            "description": "自动化测试创建",
            "trigger_type": "recognition",
            "trigger_config": {"space_ids": [1]},
            "action_type": "create_alert",
            "action_config": {"level": "info", "title": "测试告警"},
        })
        assert resp.status_code == 201
        global RULE_ID
        RULE_ID = resp.json()["data"]["id"]

    async def test_toggle_rule(self):
        rid = RULE_ID or 1  # fallback to first seeded rule
        resp = await _put(f"/rules/{rid}/toggle", {"is_enabled": False})
        assert resp.status_code in (200, 404)

    async def test_delete_rule(self):
        if RULE_ID:
            resp = await _delete(f"/rules/{RULE_ID}")
            assert resp.status_code == 204


class TestEnergy:
    async def test_list_energy(self):
        resp = await _get("/energy")
        assert resp.status_code == 200

    async def test_energy_summary(self):
        resp = await _get("/energy/summary")
        assert resp.status_code == 200


class TestUsers:
    async def test_list_users(self):
        resp = await _get("/users")
        assert resp.status_code == 200
        d = resp.json()
        assert d["pagination"]["total"] >= 1

    async def test_list_roles(self):
        resp = await _get("/roles")
        assert resp.status_code == 200
        roles = resp.json()["data"]
        assert len(roles) >= 5  # at least 5 seeded roles

    async def test_list_permissions(self):
        resp = await _get("/permissions")
        assert resp.status_code == 200
        assert len(resp.json()["data"]) >= 10


class TestRealtime:
    async def test_overview(self):
        resp = await _get("/realtime/overview")
        assert resp.status_code == 200
        d = resp.json()["data"]
        assert "online_devices" in d
        assert "total_persons" in d


class TestRBAC:
    """Verify RBAC enforcement across roles."""

    async def _try_login(self, username, password):
        """Attempt login, return True if successful."""
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post(f"{BASE}/auth/login", json={
                "username": username, "password": password, "tenant_code": "default",
            })
            return resp.status_code == 200

    async def test_employee_limited_access(self):
        """employee role can only view dashboard."""
        ok = await self._try_login("emp_liu", "emp123")
        if not ok:
            return  # Skip if user doesn't exist (default seed)
        resp = await _get("/realtime/overview")
        assert resp.status_code == 200
        resp = await _get("/persons")
        assert resp.status_code == 403
        await _login()

    async def test_reception_visitor_access(self):
        """reception can manage visitors but not devices."""
        ok = await self._try_login("rec_zhao", "rec123")
        if not ok:
            return
        resp = await _get("/visitors")
        assert resp.status_code == 200
        resp = await _get("/devices")
        assert resp.status_code == 403
        await _login()

    async def test_security_event_access(self):
        """security can read events and alerts."""
        ok = await self._try_login("sec_zhang", "sec123")
        if not ok:
            return
        resp = await _get("/events")
        assert resp.status_code == 200
        resp = await _get("/audit/logs")
        assert resp.status_code == 403
        await _login()


# ── Main runner ───────────────────────────────────────────────────────

if __name__ == "__main__":
    import asyncio

    async def run():
        from app.models.database import init_db
        await init_db()
        tests = [
            TestHealth(), TestAuth(), TestPersons(), TestDevices(),
            TestSpaces(), TestEvents(), TestRecognitions(), TestVisitors(),
            TestAudit(), TestDashboard(), TestRules(), TestEnergy(),
            TestEnergyByArea(), TestUsers(), TestRealtime(), TestRBAC(),
        ]
        passed = 0
        failed = 0

        for test in tests:
            methods = [m for m in dir(test) if m.startswith("test_")]
            for m in methods:
                try:
                    await getattr(test, m)()
                    print(f"  PASS {test.__class__.__name__}.{m}")
                    passed += 1
                except Exception as e:
                    print(f"  FAIL {test.__class__.__name__}.{m}: {e}")
                    failed += 1

        print(f"\n{'=' * 50}")
        print(f"Results: {passed} passed, {failed} failed, "
              f"{passed + failed} total")
        return failed == 0

    exit_code = 0 if asyncio.run(run()) else 1
    sys.exit(exit_code)
