#!/usr/bin/env python3
"""Simulated ESP32-S3 edge node — drives one full hub decision over MQTT.

Publishes the OPE-100 hub contract topics and subscribes to the decision
flow, then prints the resulting JSON decision. Used by the demo and by #9
terminal screen recording.

Two evidence profiles are supported, matching the hub fusion engine:

* delivery (交付路径, default group) — what shipped firmware actually
  produces: BLE beacon allowlist identity + camera motion/presence:
      edge/<edge>/motion  {"present": true, "confidence": 0.8}
      edge/<edge>/ble     {"mac", "rssi", "allowlist_hit": true}
  Scenarios: allow (dual-evidence ALLOW), deny (motion, no beacon →
  UNKNOWN-DENY), tailgate (ALERT), beacon-only (pending → timeout deny).

* research (研究/离线模式) — face/gait/BLE score messages; gait Rank-1
  86.7% is an offline research claim only.

Topics (new contract):
  edge/<hub>/status    role=hub, vela_version, cloud_link
  edge/<edge>/status   firmware, capabilities, rssi/free_heap/fps
  edge/<edge>/motion   presence evidence (delivery profile)
  edge/<edge>/ble      beacon scan / on-device allowlist hit
  edge/<edge>/face|gait  research profile
  edge/<edge>/decision  (server output, subscribed here)
  hub/<hub>/cmd         (server -> hub, also printed)

The server must already be running (``./run.sh``); with no external broker
it starts an embedded broker on 127.0.0.1:11883 — pass --port 11883.

Examples:
  python scripts/simulate_edge.py --scenario allow      # ALLOW (default)
  python scripts/simulate_edge.py --scenario deny       # UNKNOWN-DENY
  python scripts/simulate_edge.py --scenario tailgate   # TAILGATE-DETECT
  python scripts/simulate_edge.py --scenario beacon-only
  python scripts/simulate_edge.py --scenario low_face    # DEGRADE-FACE-1
  python scripts/simulate_edge.py --scenario side        # research scenario
  python scripts/simulate_edge.py --offline              # stage while down
  python scripts/simulate_edge.py --online               # replay staged

  python scripts/simulate_edge.py --host 127.0.0.1 --port 11883
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from pathlib import Path

import paho.mqtt.client as mqtt

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Chinese explanations must survive Windows GBK consoles/redirection.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

DEFAULT_HUB = "r528-hub-01"
DEFAULT_EDGE = "esp32s3-edge-01"

# Research/offline scenarios: (face, gait, ble, extra context on face msg).
RESEARCH_SCENARIOS = {
    "front": dict(face=0.90, gait=0.70, ble=0.80, ctx={}),
    "side": dict(face=0.55, gait=0.82, ble=0.75, ctx={"pose": "side"}),
    "back": dict(face=0.20, gait=0.85, ble=0.78, ctx={"pose": "back"}),
    "crowded": dict(face=0.60, gait=0.70, ble=0.70, ctx={"crowd_count": 4}),
    "low_light": dict(face=0.45, gait=0.78, ble=0.72, ctx={"light": 0.2}),
    # Face channel unreliable -> DEGRADE-FACE-1, gait+BLE carry the decision.
    "low_face": dict(face=0.20, gait=0.82, ble=0.80, ctx={}),
    "r_unknown": dict(face=0.10, gait=0.0, ble=0.10, ctx={}),
    "visitor": dict(face=0.86, gait=0.0, ble=0.72,
                    ctx={"person_type": "visitor", "visitor_valid": True}),
}

# Delivery scenarios: BLE beacon identity + camera presence.
#   beacon: allowlist_hit / None ; motion: present/confidence/extra
DELIVERY_SCENARIOS = {
    # Authorized beacon at the door + camera presence -> ALLOW.
    "allow": dict(
        beacon=dict(allowlist_hit=True, rssi=-52),
        motion=dict(present=True, confidence=0.82),
    ),
    # Motion detected, BLE scan finds no allowlisted beacon -> UNKNOWN-DENY.
    "deny": dict(
        beacon=dict(allowlist_hit=False, rssi=-78),
        motion=dict(present=True, confidence=0.80),
        order=("motion", "beacon"),
    ),
    # Authorized holder followed by a second person -> ALERT, manual review.
    "tailgate": dict(
        beacon=dict(allowlist_hit=True, rssi=-52),
        motion=dict(present=True, confidence=0.85, tailgate=True),
    ),
    # Beacon seen, no one ever confirmed at the door: pending then deny.
    "beacon-only": dict(
        beacon=dict(allowlist_hit=True, rssi=-52),
        motion=None,
        wait=6.0,
    ),
}

SCENARIOS = {**DELIVERY_SCENARIOS, **RESEARCH_SCENARIOS}


def log(msg: str) -> None:
    print(f"[edge-sim] {msg}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Simulated VelaMesh edge node")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--username", default="")
    parser.add_argument("--password", default="")
    parser.add_argument("--hub", default=DEFAULT_HUB)
    parser.add_argument("--edge", default=DEFAULT_EDGE)
    parser.add_argument(
        "--scenario", choices=sorted(SCENARIOS), default="allow"
    )
    parser.add_argument("--person-id", type=int, default=9001)
    parser.add_argument("--person-name", default="张伟(模拟)")
    parser.add_argument("--offline", action="store_true",
                        help="declare hub cloud link offline before sending evidence")
    parser.add_argument("--online", action="store_true",
                        help="declare cloud link online (triggers replay), then exit")
    parser.add_argument("--no-decision-wait", action="store_true")
    args = parser.parse_args()

    is_delivery = args.scenario in DELIVERY_SCENARIOS
    decisions: list[dict] = []
    connected_evt = threading.Event()

    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id="sim-edge-node",
        protocol=mqtt.MQTTv311,
    )
    if args.username:
        client.username_pw_set(args.username, args.password or None)

    def on_connect(c, userdata, flags, reason_code, properties):
        log(f"connected to {args.host}:{args.port} (rc={reason_code})")
        c.subscribe(f"edge/{args.edge}/decision")
        c.subscribe(f"hub/{args.hub}/cmd")
        c.subscribe("vela/decision")
        connected_evt.set()

    seen_event_ids: set = set()

    def on_message(c, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except Exception:
            return
        if msg.topic.endswith("/cmd"):
            log(f"CMD received on {msg.topic}: {json.dumps(payload, ensure_ascii=False)}")
            return
        # The server fans one decision out on both vela/decision and
        # edge/<id>/decision; print it once.
        event_id = payload.get("event_id")
        if event_id is not None and event_id in seen_event_ids:
            return
        if event_id is not None:
            seen_event_ids.add(event_id)
        log("=== DECISION JSON ===")
        print(json.dumps(payload, ensure_ascii=False, indent=2), flush=True)
        decisions.append(payload)

    client.on_connect = on_connect
    client.on_message = on_message

    # With MQTT_MODE=auto a brokerless demo runs the embedded fallback on
    # 11883; retry it automatically when the default 1883 is refused.
    candidate_ports = [args.port]
    if args.port == 1883:
        candidate_ports.append(11883)
    connected_port = None
    last_exc: OSError | None = None
    for port in candidate_ports:
        try:
            client.connect(args.host, port, keepalive=30)
            connected_port = port
            break
        except OSError as exc:
            last_exc = exc
            log(f"broker {args.host}:{port} unreachable ({exc})")
    if connected_port is None:
        log(f"ERROR: no MQTT broker reachable from {candidate_ports}: {last_exc}")
        log("Start the server first (./run.sh); embedded fallback listens on 11883.")
        return 2
    args.port = connected_port
    client.loop_start()
    if not connected_evt.wait(timeout=5):
        log("ERROR: MQTT connect timeout")
        return 2

    def pub(topic: str, payload: dict, delay: float = 0.4):
        client.publish(topic, json.dumps(payload, ensure_ascii=False), qos=1)
        log(f"-> {topic} {json.dumps(payload, ensure_ascii=False)[:170]}")
        time.sleep(delay)

    try:
        # 1) Hub heartbeat (R528, openvela).
        pub(f"edge/{args.hub}/status", {
            "node_id": args.hub, "role": "hub",
            "model": "Gemini-S1/R528", "vela_version": "openvela-1.3",
            "firmware_ver": "hub-2026.09.20", "ip": "10.6.40.22",
            "cloud_link": "offline" if args.offline else "online",
            "capabilities": ["fusion", "ble_gateway"],
        })

        if args.online:
            pub(f"edge/{args.hub}/status", {
                "node_id": args.hub, "role": "hub",
                "cloud_link": "online",
            })
            log("cloud link restored; queued events will replay server-side")
            time.sleep(2.0)
            return 0

        # 2) Edge node heartbeat with capabilities + telemetry.
        edge_caps = (["ble", "camera"] if is_delivery
                     else ["face", "gait", "ble", "camera"])
        pub(f"edge/{args.edge}/status", {
            "node_id": args.edge, "hub_id": args.hub,
            "firmware_ver": "edge-2026.09.20",
            "capabilities": edge_caps,
            "rssi": -52, "free_heap": 182340, "fps": 14.5, "light": 0.9,
        })

        if is_delivery:
            rc = _run_delivery(args, pub)
            wait_s = rc
        else:
            rc = _run_research(args, pub)
            wait_s = 8.0

        if args.no_decision_wait:
            return 0
        deadline = time.time() + wait_s
        while time.time() < deadline and not decisions:
            time.sleep(0.1)
        if decisions:
            d = decisions[0]
            log(f"scenario={args.scenario} -> {d.get('policy_id')} "
                f"action={d.get('action')} conf={d.get('confidence')} "
                f"mode={d.get('evidence_mode', 'research')}")
            return 0
        log("WARN: no decision received within the wait window "
            "(check the server log; pending windows wait for more modalities)")
        return 1
    finally:
        client.loop_stop()
        client.disconnect()


def _run_delivery(args, pub) -> float:
    """Send BLE beacon + camera presence evidence; returns decision wait."""
    script = DELIVERY_SCENARIOS[args.scenario]
    base = f"edge/{args.edge}"
    wait_s = script.get("wait", 8.0)

    def send_beacon():
        b = script["beacon"]
        if b is None:
            return
        payload = {
            "node_id": args.edge, "hub_id": args.hub,
            "mac": "AA:BB:CC:DD:EE:01", "rssi": b.get("rssi", -60),
        }
        if b.get("allowlist_hit"):
            # On-device allowlist match (firmware does the MAC check).
            payload.update({
                "allowlist_hit": True,
                "person_name": args.person_name,
                "ble_enabled": True,
            })
        pub(f"{base}/ble", payload)

    def send_motion():
        m = script["motion"]
        if m is None:
            return
        payload = {
            "node_id": args.edge, "hub_id": args.hub,
            "firmware_ver": "edge-2026.09.20",
            **m,
        }
        pub(f"{base}/motion", payload)

    order = script.get("order", ("beacon", "motion"))
    for step in order:
        if step == "beacon":
            send_beacon()
        else:
            send_motion()
    return wait_s


def _run_research(args, pub) -> float:
    """Send face/gait/BLE score evidence (research/offline profile)."""
    script = RESEARCH_SCENARIOS[args.scenario]
    ctx = dict(script["ctx"])
    person_type = ctx.pop("person_type", "employee")
    visitor_valid = ctx.pop("visitor_valid", None)
    name = "访客(模拟)" if person_type == "visitor" else args.person_name
    base = f"edge/{args.edge}"

    if script["face"] > 0:
        face_msg = {
            "node_id": args.edge, "hub_id": args.hub,
            "score": script["face"],
            "person_id": args.person_id if script["face"] >= 0.3 else None,
            "person_name": name, "person_type": person_type,
            "light": ctx.get("light", 0.9),
            "firmware_ver": "edge-2026.09.20",
            **ctx,
        }
        if visitor_valid is not None:
            face_msg["visitor_valid"] = visitor_valid
        pub(f"{base}/face", face_msg)

    if script["gait"] > 0:
        pub(f"{base}/gait", {
            "node_id": args.edge, "hub_id": args.hub,
            "score": script["gait"], "person_id": args.person_id,
            "person_name": name, "person_type": person_type,
        })

    if script["ble"] > 0:
        ble_matched = script["ble"] >= 0.4 and args.scenario != "r_unknown"
        ble_msg = {
            "node_id": args.edge, "hub_id": args.hub,
            "mac": "AA:BB:CC:DD:EE:01", "rssi": -52,
            "matched": ble_matched,
            "score": script["ble"] * (0.6 if ble_matched else 0.1),
            "person_id": args.person_id if ble_matched else None,
            "person_name": name if ble_matched else "",
            "person_type": person_type,
        }
        if visitor_valid is not None:
            ble_msg["visitor_valid"] = visitor_valid
        pub(f"{base}/ble", ble_msg)
    return 8.0


if __name__ == "__main__":
    sys.exit(main())
