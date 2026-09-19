"""Gait MQTT adapter: ``dominiscius/+/gait/result`` -> unified demo event.

The ESP32 gait pipeline (OPE-73) publishes recognition results on the
``dominiscius/+/gait/result`` topic. That topic root is owned by the ESP32
firmware and is intentionally separate from the OpenVela ``vela/node/+/+``
namespace used by the rest of the demo. This adapter subscribes to the gait
topic, normalizes the device payload into the frontend's unified
``gait_result`` event, persists it through the shared demo telemetry path, and
fans it out to the demo WebSocket.

Scope (per OPE-86 latest instruction): protocol adaptation only.
- The ESP32 MQTT topic is NOT modified.
- The BLE protocol is NOT modified.
- No face/BLE fusion, no cloud MQTT, no model changes, no ESP32 changes.
"""

from __future__ import annotations

import logging
from typing import Any

from app.services.demo_event_bus import demo_event_bus
from app.services.demo_telemetry import DEFAULT_TENANT_ID, demo_telemetry

logger = logging.getLogger("demo.gait")

# ESP32 gait/result topic. Kept literal (not derived from MQTT_TOPIC_PREFIX)
# because the ESP32 firmware owns this topic and must not be changed.
# Legacy topic root: this spelling is hard-coded in shipped ESP32 firmware
# and is independent of the MQTT_TOPIC_PREFIX="vela" namespace; do not rename.
GAIT_TOPIC_ROOT = "dominiscius"
GAIT_TOPIC_PATTERN = "dominiscius/+/gait/result"


def _first(value: Any, *keys: str) -> Any:
    """Return the first non-null value found under ``keys`` in a dict."""
    if not isinstance(value, dict):
        return None
    for key in keys:
        if key in value and value[key] is not None:
            return value[key]
    return None


def _round(value: Any) -> Any:
    """Round numeric values to 4dp for stable display; pass non-numbers through."""
    return round(float(value), 4) if isinstance(value, (int, float)) else value


def _as_latency_ms(timing: Any) -> float | None:
    """Extract a latency in milliseconds from the device ``timing`` field.

    The ESP32 may send ``timing`` as a scalar (ms) or as a dict with one of
    several common keys. We try them in order of specificity.
    """
    if isinstance(timing, (int, float)):
        return float(timing)
    if isinstance(timing, dict):
        for key in ("total_ms", "latency_ms", "inference_ms", "elapsed_ms", "duration_ms", "ms", "total"):
            value = timing.get(key)
            if isinstance(value, (int, float)):
                return float(value)
    return None


def _top1(top3: Any) -> dict[str, Any] | None:
    """Return the best match from a top-3 list, or a scalar top-1 dict."""
    if isinstance(top3, list) and top3:
        candidate = top3[0]
        return candidate if isinstance(candidate, dict) else None
    if isinstance(top3, dict):
        return top3
    return None


def _compact_top3(top3: Any) -> list[dict[str, Any]]:
    """Reduce each top-3 entry to {identity, score} for compact UI display."""
    if not isinstance(top3, list):
        return []
    compact: list[dict[str, Any]] = []
    for item in top3[:3]:
        if not isinstance(item, dict):
            continue
        compact.append({
            "identity": _first(item, "identity", "label", "name", "id", "person_name") or "unknown",
            "score": _round(_first(item, "score", "similarity", "cosine", "confidence")),
        })
    return compact


class GaitAdapter:
    """Subscribe to ``dominiscius/+/gait/result`` and emit unified gait events."""

    @property
    def topic_pattern(self) -> str:
        return GAIT_TOPIC_PATTERN

    def transform(self, topic: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Map a device gait/result payload to the unified event payload.

        Input (ESP32, ``dominiscius/<node_id>/gait/result``)::

            {"session_id", "direction", "top3", "cosine", "margin", "timing"}

        Output (unified frontend event ``payload``)::

            {"identity", "score", "direction", "source": "gait",
             "session_id", "latency", "node_id", "cosine", "margin", "top3"}
        """
        parts = topic.split("/")
        node_id = str(payload.get("node_id") or (parts[1] if len(parts) > 1 else "unknown"))
        session_id = payload.get("session_id")
        direction = payload.get("direction")
        cosine = payload.get("cosine")
        margin = payload.get("margin")
        top3 = payload.get("top3")
        top1 = _top1(top3)

        identity = _first(top1 or {}, "identity", "label", "name", "id", "person_name") or "unknown"
        score = _first(top1 or {}, "score", "similarity", "cosine", "confidence")
        if score is None and isinstance(cosine, (int, float)):
            # Fall back to the top-level cosine if the top-1 entry lacks a score.
            score = cosine

        unified: dict[str, Any] = {
            "identity": identity,
            "score": _round(score),
            "direction": direction,
            "source": "gait",
            "session_id": session_id,
            "latency": _as_latency_ms(payload.get("timing")),
            # Extra evidence retained for the UI / audit beyond the minimal contract.
            "node_id": node_id,
            "cosine": _round(cosine),
            "margin": _round(margin),
            "top3": _compact_top3(top3),
        }
        return {"node_id": node_id, "payload": unified}

    async def on_message(self, topic: str, payload: dict[str, Any]) -> None:
        """MQTT callback registered against ``dominiscius/+/gait/result``."""
        try:
            event = self.transform(topic, payload)
        except Exception:
            logger.exception("Failed to transform gait payload on %s", topic)
            return

        unified = event["payload"]

        # Persist through the shared telemetry path so the gait channel shows
        # up in node evidence, coverage accounting, and the REST snapshot. The
        # node_id/channel are passed explicitly because the dominiscius topic
        # root does not match the vela/node/<id>/<channel> parsing in ingest().
        try:
            await demo_telemetry.ingest(
                topic,
                {"node_id": event["node_id"], "channel": "gait", **unified},
                persist=True,
                provenance="real",
            )
        except Exception:
            logger.exception("Failed to persist gait telemetry from %s", topic)

        # Fan out the spec-compliant unified event to the demo WebSocket.
        await demo_event_bus.publish(
            "gait_result",
            unified,
            tenant_id=DEFAULT_TENANT_ID,
        )
        logger.info(
            "[Gait] node=%s identity=%s score=%s direction=%s latency=%s session=%s",
            event["node_id"],
            unified.get("identity"),
            unified.get("score"),
            unified.get("direction"),
            unified.get("latency"),
            unified.get("session_id"),
        )


gait_adapter = GaitAdapter()
