#!/usr/bin/env python3
"""API tests for the OPE-100 topology surface (/api/hubs, /api/edges, ...)."""

import sys

sys.path.insert(0, "..")

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.main import create_app  # noqa: E402
from app.models.database import init_db  # noqa: E402

app = create_app()
transport = ASGITransport(app=app)


@pytest.fixture(autouse=True)
async def _setup():
    await init_db()
    yield


async def _client():
    return AsyncClient(transport=transport, base_url="http://test")


async def _auth(ac: AsyncClient):
    resp = await ac.post("/api/auth/login", json={
        "username": "admin", "password": "admin123", "tenant_code": "default",
    })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    token = body.get("access_token") or body.get("data", {}).get("access_token")
    ac.headers["Authorization"] = f"Bearer {token}"


async def test_topology_graph_endpoint():
    async with await _client() as ac:
        await _auth(ac)
        resp = await ac.get("/api/topology")
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert "hubs" in data and "mqtt" in data
        assert data["hub_count"] >= 1


async def test_hub_and_edge_lifecycle_and_command():
    hid = "api-hub-a1"
    eid = "api-edge-a1"
    async with await _client() as ac:
        await _auth(ac)

        # Register hub + edge.
        resp = await ac.post("/api/hubs", json={
            "id": hid, "name": "API测试中枢", "vela_version": "openvela-1.3",
        })
        assert resp.status_code == 201, resp.text
        resp = await ac.post("/api/edges", json={
            "id": eid, "hub_id": hid, "capabilities": ["ble", "camera"],
        })
        assert resp.status_code == 201, resp.text

        resp = await ac.get("/api/hubs")
        assert resp.status_code == 200
        assert any(h["id"] == hid for h in resp.json()["data"])
        resp = await ac.get("/api/edges", params={"hub_id": hid})
        edge = next(e for e in resp.json()["data"] if e["id"] == eid)
        assert edge["capabilities"] == ["ble", "camera"]

        resp = await ac.get(f"/api/hubs/{hid}")
        assert resp.json()["data"]["id"] == hid

        # Heartbeats.
        assert (await ac.post(f"/api/hubs/{hid}/heartbeat", json={
            "cloud_link": "online"})).status_code == 200
        assert (await ac.post(f"/api/edges/{eid}/heartbeat", json={
            "rssi": -55, "fps": 14.0})).status_code == 200

        # Command published to hub/<id>/cmd.
        resp = await ac.post(f"/api/hubs/{hid}/command", json={
            "cmd": "open_door", "params": {"duration": 3}})
        assert resp.status_code == 200
        assert resp.json()["data"]["mqtt_topic"] == f"hub/{hid}/cmd"

        # Cloud-link toggle (degrade demo).
        resp = await ac.post(f"/api/hubs/{hid}/cloud-link",
                             json={"state": "offline"})
        assert resp.json()["data"]["cloud_link"] == "offline"
        resp = await ac.post(f"/api/hubs/{hid}/cloud-link",
                             json={"state": "online"})
        assert resp.json()["data"]["cloud_link"] == "online"

        # Offline queue read + force replay.
        assert (await ac.get("/api/offline-queue")).status_code == 200
        assert (await ac.post("/api/offline-queue/replay")).status_code == 200

        # Teardown.
        assert (await ac.delete(f"/api/edges/{eid}")).status_code == 204
        assert (await ac.delete(f"/api/hubs/{hid}")).status_code == 204


async def test_unknown_hub_and_edge_return_404():
    async with await _client() as ac:
        await _auth(ac)
        assert (await ac.get("/api/hubs/no-such-hub")).status_code == 404
        assert (await ac.delete("/api/hubs/no-such-hub")).status_code == 404
        assert (await ac.delete("/api/edges/no-such-edge")).status_code == 404
