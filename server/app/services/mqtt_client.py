"""MQTT client service wrapping paho-mqtt for async usage."""

import asyncio
import inspect
import json
import logging
import threading
import time
from typing import Callable

import paho.mqtt.client as mqtt

from app.config import settings

logger = logging.getLogger("mqtt")


class MqttClient:
    """Async-friendly MQTT client that connects to mosquitto/EMQX broker.

    Supports an automatic fallback to the in-process demo broker so the
    server starts with zero external dependencies (MQTT_MODE=auto, the
    default). ``mode`` reports "external" or "embedded" after start.
    """

    def __init__(self):
        self._broker_host = settings.MQTT_BROKER
        self._broker_port = settings.MQTT_PORT
        self._embedded = None
        self.mode = "external"
        self.client = self._build_client()
        self._message_handlers: dict[str, list[Callable]] = {}
        self._connected = threading.Event()
        self._loop = None
        self._last_connected_at: float | None = None
        self._last_disconnect_rc: int | None = None

    def _build_client(self) -> mqtt.Client:
        client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            # Legacy client-id spelling kept for broker ACL/back-compat.
            client_id=settings.MQTT_CLIENT_ID,
            protocol=mqtt.MQTTv311,
        )
        if settings.MQTT_USERNAME:
            client.username_pw_set(
                settings.MQTT_USERNAME, settings.MQTT_PASSWORD or None
            )
        client.on_connect = self._on_connect
        client.on_message = self._on_message
        client.on_disconnect = self._on_disconnect
        return client

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            logger.info(f"MQTT connected to {settings.MQTT_BROKER}:{settings.MQTT_PORT}")
            self._connected.set()
            self._last_connected_at = time.time()
            self._last_disconnect_rc = None
            # Subscribe to all node topics
            client.subscribe(f"{settings.MQTT_TOPIC_PREFIX}/node/+/+")
            # Re-subscribe every topic registered via subscribe() so they
            # survive reconnects. The wildcard above only covers the
            # vela/node namespace; topics on other roots (e.g. the ESP32
            # ``dominiscius/+/gait/result`` gait topic) would otherwise be
            # silently dropped after a reconnect.
            for topic in self._message_handlers:
                client.subscribe(topic)
        else:
            logger.error(f"MQTT connection failed (reason={reason_code})")

    def _on_disconnect(self, client, userdata, flags, reason_code, properties):
        logger.warning(f"MQTT disconnected (reason={reason_code})")
        self._connected.clear()
        self._last_disconnect_rc = getattr(reason_code, "value", reason_code)

    def _on_message(self, client, userdata, msg):
        """Route incoming MQTT messages to registered handlers."""
        topic = msg.topic
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            logger.warning(f"MQTT invalid payload on {topic}")
            return
        if not isinstance(payload, dict):
            logger.warning(f"MQTT payload on {topic} must be a JSON object")
            return

        # Notify matching handlers
        for pattern, handlers in self._message_handlers.items():
            if _topic_matches(pattern, topic):
                for handler in handlers:
                    try:
                        if inspect.iscoroutinefunction(handler):
                            # Async handler (e.g. identity_engine.on_face) —
                            # schedule on the main event loop. paho runs _on_message
                            # in its own thread, so we must hop back to the loop.
                            if self._loop:
                                fut = asyncio.run_coroutine_threadsafe(
                                    handler(topic, payload), self._loop
                                )
                                # Log exceptions instead of silently swallowing
                                # them (an un-awaited future's exception would
                                # otherwise be lost).
                                def _log_failure(f, h=handler, t=topic):
                                    if f.cancelled():
                                        return
                                    exc = f.exception()
                                    if exc is not None:
                                        logger.exception(
                                            f"MQTT async handler {getattr(h, '__name__', h)} "
                                            f"failed on {t}: {exc}",
                                            exc_info=exc,
                                        )
                                fut.add_done_callback(_log_failure)
                            else:
                                logger.error("MQTT async handler but no event loop bound")
                        else:
                            handler(topic, payload)
                    except Exception as e:
                        logger.error(f"MQTT handler error: {e}")

    async def _probe_external(self) -> bool:
        """TCP-reachability probe for the configured external broker."""
        try:
            fut = asyncio.open_connection(settings.MQTT_BROKER, settings.MQTT_PORT)
            reader, writer = await asyncio.wait_for(
                fut, timeout=settings.MQTT_CONNECT_TIMEOUT
            )
            writer.close()
            try:
                await writer.wait_closed()
            except (OSError, RuntimeError):
                pass
            return True
        except (OSError, asyncio.TimeoutError, ConnectionRefusedError):
            return False

    async def start_embedded(self) -> tuple[str, int]:
        from app.services.embedded_broker import EmbeddedMqttBroker

        self._embedded = EmbeddedMqttBroker(
            host=settings.MQTT_EMBEDDED_LISTEN_HOST,
            port=settings.MQTT_EMBEDDED_LISTEN_PORT,
        )
        host, port = await self._embedded.start()
        self._broker_host, self._broker_port = host, port
        self.mode = "embedded"
        return host, port

    async def start(self):
        """Choose a broker and connect (call from the async app lifespan).

        MQTT_MODE:
          external — require MQTT_BROKER:MQTT_PORT;
          embedded — always start the in-process demo broker;
          auto (default) — use the configured broker when reachable,
          otherwise start the in-process broker so run.sh always works.
        """
        self._loop = asyncio.get_running_loop()
        mode = settings.MQTT_MODE
        use_embedded = mode == "embedded"
        if mode == "auto" and not await self._probe_external():
            logger.warning(
                "MQTT broker %s:%s unreachable; falling back to embedded broker",
                settings.MQTT_BROKER, settings.MQTT_PORT,
            )
            use_embedded = True
        if use_embedded:
            await self.start_embedded()

        logger.info("Connecting MQTT to %s:%s (mode=%s)", self._broker_host, self._broker_port, self.mode)
        self.client.connect_async(self._broker_host, self._broker_port, keepalive=60)
        self.client.loop_start()

    def start_sync(self):
        """Legacy synchronous starter; kept for non-lifespan callers/tests."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(self.start())
                return
        except RuntimeError:
            pass
        asyncio.run(self.start())

    async def stop(self):
        """Disconnect and, when we own it, stop the embedded broker."""
        try:
            self.client.loop_stop()
            self.client.disconnect()
        except Exception:
            pass
        if self._embedded is not None:
            await self._embedded.stop()
            self._embedded = None
        logger.info("MQTT disconnected (mode=%s)", self.mode)

    @property
    def broker_host(self) -> str:
        return self._broker_host

    @property
    def broker_port(self) -> int:
        return self._broker_port

    def subscribe(self, topic: str, handler: Callable):
        """Register a handler for a topic pattern."""
        if topic not in self._message_handlers:
            self._message_handlers[topic] = []
        self._message_handlers[topic].append(handler)
        self.client.subscribe(topic)

    def publish(self, topic: str, payload: dict):
        """Publish a JSON message to a topic."""
        self.client.publish(topic, json.dumps(payload), qos=1)

    @property
    def is_connected(self) -> bool:
        return self._connected.is_set()

    @property
    def connection_state(self) -> dict:
        return {
            "connected": self.is_connected,
            "last_connected_at": self._last_connected_at,
            "last_disconnect_rc": self._last_disconnect_rc,
        }


def _topic_matches(pattern: str, topic: str) -> bool:
    """Simple MQTT topic wildcard matching for '+' and '#'."""
    pattern_parts = pattern.split("/")
    topic_parts = topic.split("/")

    for i, pp in enumerate(pattern_parts):
        if pp == "#":
            return True
        if i >= len(topic_parts):
            return False
        if pp == "+":
            continue
        if pp != topic_parts[i]:
            return False
    return len(pattern_parts) == len(topic_parts)


# Singleton
mqtt_client = MqttClient()
