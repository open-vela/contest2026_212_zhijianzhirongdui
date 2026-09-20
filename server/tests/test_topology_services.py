#!/usr/bin/env python3
"""Topology, offline-queue and MiMo surface tests (OPE-100).

Uses the same seeded SQLite database as the API suite; every fixture uses
unique ids so it does not collide with the default demo hub.
"""

import sys

sys.path.insert(0, "..")

import pytest  # noqa: E402

from app.models.database import init_db  # noqa: E402
from app.services.cloud_state import cloud_state  # noqa: E402
from app.services.hub_offline import hub_offline  # noqa: E402
from app.services.mimo_client import mimo_client  # noqa: E402
from app.services.topology import topology  # noqa: E402


@pytest.fixture(autouse=True)
async def _setup():
    await init_db()
    yield


async def test_register_hub_and_edge_and_list():
    hid = "test-hub-t1"
    eid = "test-edge-t1"
    hub = await topology.register_hub({
        "id": hid, "name": "测试中枢", "model": "Gemini-S1/R528",
        "vela_version": "openvela-1.3",
    })
    assert hub.id == hid
    edge = await topology.register_edge({
        "id": eid, "hub_id": hid, "capabilities": ["ble", "camera"],
    })
    assert edge.hub_id == hid
    assert edge.cap_ble and edge.cap_camera and not edge.cap_face

    hubs = await topology.list_hubs()
    target = next(h for h in hubs if h["id"] == hid)
    assert target["model"] == "Gemini-S1/R528"
    assert any(e["id"] == eid for e in target["edges"])
    assert await topology.hub_for_edge(eid) == hid

    edges = await topology.list_edges(hid)
    assert [e["id"] for e in edges] == [eid]

    assert await topology.deregister_edge(eid)
    assert await topology.deregister_hub(hid)


async def test_edge_heartbeat_records_telemetry():
    hid = "test-hub-t2"
    eid = "test-edge-t2"
    await topology.edge_heartbeat(eid, {
        "hub_id": hid, "firmware_ver": "edge-fw",
        "capabilities": ["ble"], "rssi": -61, "free_heap": 200000,
        "fps": 12.0,
    })
    edges = await topology.list_edges(hid)
    edge = next(e for e in edges if e["id"] == eid)
    assert edge["is_online"] is True
    assert edge["telemetry"]["rssi"] == -61
    assert edge["telemetry"]["free_heap"] == 200000
    await topology.mark_edge_offline(eid)
    edge = next(e for e in await topology.list_edges(hid) if e["id"] == eid)
    assert edge["is_online"] is False
    await topology.deregister_edge(eid)
    await topology.deregister_hub(hid)


async def test_cloud_link_and_offline_staging_replay():
    hid = "test-hub-t3"
    eid = "test-edge-t3"
    await topology.register_hub({"id": hid})
    # Forced offline (demo degrade switch) makes cloud_state report offline.
    cloud_state.force(hid, "offline")
    state = await topology.set_cloud_link(hid, "offline")
    assert state == "offline"
    assert cloud_state.is_offline(hid)

    for channel, topic in (
        ("status", f"edge/{eid}/status"),
        ("ble", f"edge/{eid}/ble"),
    ):
        await hub_offline.enqueue(
            hub_id=hid, edge_id=eid, channel=channel,
            topic=topic, payload={"k": channel},
        )
    assert await hub_offline.depth(hid) == 2

    # Replay hands rows into the cloud outbox and clears the staging queue.
    replayed = await hub_offline.replay(hid)
    assert replayed == 2
    assert await hub_offline.depth(hid) == 0

    cloud_state.clear_force(hid)
    await topology.deregister_hub(hid)


def test_mimo_surface_is_mock_without_key():
    # No API key is configured in the test environment: cloud inference must
    # not be claimed.
    assert mimo_client.configured is False
    assert mimo_client.mode == "mock"


async def test_mimo_mock_intent_and_explain():
    intent = await mimo_client.infer_intent({"scenario": "front"})
    assert intent["mode"] == "mock"
    assert intent["intent"]
    explained = await mimo_client.explain_decision(
        {"policy_id": "UNKNOWN-DENY", "explanation": "测试"}
    )
    assert explained["mode"] == "mock"
    assert "NO_IDENTITY" in explained["reason_codes"]
