#!/usr/bin/env python3
"""Tests for the demo-fallback embedded MQTT broker (OPE-100)."""

import asyncio
import json
import sys

sys.path.insert(0, "..")

import pytest  # noqa: E402
import paho.mqtt.client as mqtt  # noqa: E402

from app.services.embedded_broker import EmbeddedMqttBroker, topic_matches  # noqa: E402


@pytest.mark.parametrize(
    "pattern,topic,expected",
    [
        ("edge/+/ble", "edge/n1/ble", True),
        ("edge/+/ble", "edge/n1/face", False),
        ("edge/#", "edge/n1/a/b", True),
        ("vela/node/+/+", "vela/node/1/face", True),
        ("vela/node/+/+", "vela/node/1", False),
        ("a/b", "a/b/c", False),
    ],
)
def test_topic_matching(pattern, topic, expected):
    assert topic_matches(pattern, topic) is expected


async def test_broker_pubsub_roundtrip_qos1():
    broker = EmbeddedMqttBroker(host="127.0.0.1", port=0)
    host, port = await broker.start()
    try:
        got: asyncio.Queue = asyncio.Queue()
        sub_ready = asyncio.Event()

        sub = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id="test-sub", protocol=mqtt.MQTTv311,
        )

        def on_sub_connect(c, u, f, rc, p):
            c.subscribe("edge/n1/decision", qos=1)

        def on_sub_msg(c, u, m):
            got.put_nowait(json.loads(m.payload))

        sub.on_connect = on_sub_connect
        sub.on_message = on_sub_msg
        sub.connect(host, port)
        sub.loop_start()

        pub = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id="test-pub", protocol=mqtt.MQTTv311,
        )
        pub_connected = asyncio.Event()

        def on_pub_connect(c, u, f, rc, p):
            pub_connected.set()

        pub.on_connect = on_pub_connect
        pub.connect(host, port)
        pub.loop_start()

        try:
            await asyncio.wait_for(pub_connected.wait(), 5)
            # Give the subscriber a moment to register its filter.
            await asyncio.sleep(0.5)
            info = pub.publish(
                "edge/n1/decision", json.dumps({"action": "allow"}), qos=1
            )
            assert info.rc == mqtt.MQTT_ERR_SUCCESS
            delivered = await asyncio.wait_for(got.get(), 5)
            assert delivered["action"] == "allow"
        finally:
            for client in (sub, pub):
                client.disconnect()
                client.loop_stop()
    finally:
        await broker.stop()
