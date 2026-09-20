"""Minimal in-process MQTT 3.1.1 broker for the offline demo fallback.

When neither EMQX nor a local mosquitto is reachable (``MQTT_MODE=auto``),
the server starts this tiny broker on 127.0.0.1:11883 so ``run.sh`` still
comes up with one command and simulated edge nodes / the demo script can
publish over real MQTT sockets.

Scope is deliberately small and sufficient for the demo only:
- MQTT 3.1.1 CONNECT/CONNACK (anonymous; username/password accepted but not
  checked), PINGREQ/PINGRESP, DISCONNECT, SUBSCRIBE/SUBACK, PUBLISH/QoS0
  and QoS1 (PUBACK retained, no retransmission), QoS2 is downgraded.
- '+' / '#' topic matching, no retained messages, no will messages.

This is NOT a production broker: single process, in-memory sessions, no TLS,
no persistence, no auth. Use mosquitto/EMQX for any real deployment.
"""

from __future__ import annotations

import asyncio
import logging
import socket
import struct

logger = logging.getLogger("mqtt.embedded")


def topic_matches(pattern: str, topic: str) -> bool:
    pp = pattern.split("/")
    tp = topic.split("/")
    for i, part in enumerate(pp):
        if part == "#":
            return True
        if i >= len(tp):
            return False
        if part != "+" and part != tp[i]:
            return False
    return len(pp) == len(tp)


class _Session:
    def __init__(self, writer: asyncio.StreamWriter):
        self.writer = writer
        self.subscriptions: set[str] = set()


class EmbeddedMqttBroker:
    def __init__(self, host: str = "127.0.0.1", port: int = 11883) -> None:
        self.host = host
        self.port = port
        self._server: asyncio.AbstractServer | None = None
        self._sessions: dict[str, _Session] = {}

    @property
    def is_running(self) -> bool:
        return self._server is not None

    async def start(self) -> tuple[str, int]:
        self._server = await asyncio.start_server(self._handle, self.host, self.port)
        # Resolve the actual port (0 = OS-assigned).
        sock: socket.socket = self._server.sockets[0]
        self.host, self.port = sock.getsockname()[:2]
        logger.info("Embedded MQTT broker listening on %s:%s (demo fallback)", self.host, self.port)
        return self.host, self.port

    async def stop(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    # ── Packet helpers ────────────────────────────────────────────────

    @staticmethod
    def _encode_remaining_length(n: int) -> bytes:
        out = bytearray()
        while True:
            byte = n % 128
            n //= 128
            if n:
                byte |= 0x80
            out.append(byte)
            if not n:
                return bytes(out)

    @staticmethod
    def _read_string(data: bytes, offset: int) -> tuple[str, int]:
        (length,) = struct.unpack_from("!H", data, offset)
        offset += 2
        value = data[offset:offset + length].decode("utf-8", "replace")
        return value, offset + length

    @staticmethod
    def _packet(packet_type: int, variable: bytes = b"", flags: int = 0) -> bytes:
        return bytes([(packet_type << 4) | flags]) + EmbeddedMqttBroker._encode_remaining_length(len(variable)) + variable

    # ── Per-connection loop ───────────────────────────────────────────

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        session = _Session(writer)
        client_id = f"peer-{id(writer):x}"
        try:
            while True:
                first = await reader.readexactly(1)
                ptype = first[0] >> 4
                pflags = first[0] & 0x0F
                # Remaining length is a 1-4 byte variable-length integer.
                remaining = 0
                multiplier = 1
                while True:
                    b = (await reader.readexactly(1))[0]
                    remaining += (b & 0x7F) * multiplier
                    if not b & 0x80:
                        break
                    multiplier *= 128
                payload = await reader.readexactly(remaining) if remaining else b""
                pos = 0

                if ptype == 1:  # CONNECT
                    pos += 2  # protocol name length
                    proto = payload[pos:pos + 4]
                    pos += 4
                    level = payload[pos]
                    pos += 1
                    connect_flags = payload[pos]
                    pos += 1
                    pos += 2  # keep alive
                    cid, pos = self._read_string(payload, pos)
                    if cid:
                        client_id = cid
                    self._sessions[client_id] = session
                    session_clean = bool(connect_flags & 0x02)
                    # CONNACK: session present=0, return code 0 (accepted)
                    writer.write(self._packet(2, bytes([0x01 if not session_clean else 0x00, 0x00])))
                    await writer.drain()
                    logger.debug("embedded broker: CONNECT client=%s proto=%s level=%s", client_id, proto, level)
                elif ptype == 3:  # PUBLISH
                    dup = bool(pflags & 0x08)
                    qos = (pflags >> 1) & 0x03
                    topic, pos = self._read_string(payload, pos)
                    packet_id = None
                    if qos in (1, 2):
                        (packet_id,) = struct.unpack_from("!H", payload, pos)
                        pos += 2
                    body = payload[pos:]
                    await self._deliver(topic, body, qos, packet_id, session)
                    if qos == 1 and packet_id is not None:
                        # PUBACK so the publisher's inflight message completes
                        # (paho waits on these during a clean disconnect).
                        writer.write(self._packet(4, struct.pack("!H", packet_id)))
                        await writer.drain()
                elif ptype == 8:  # SUBSCRIBE
                    (packet_id,) = struct.unpack_from("!H", payload, pos)
                    pos += 2
                    granted = []
                    while pos < len(payload):
                        filter_str, pos = self._read_string(payload, pos)
                        req_qos = payload[pos]
                        pos += 1
                        session.subscriptions.add(filter_str)
                        granted.append(min(req_qos, 1))  # max QoS1 supported
                    variable = struct.pack("!H", packet_id) + bytes(granted)
                    writer.write(self._packet(9, variable))
                    await writer.drain()
                elif ptype == 10:  # UNSUBSCRIBE
                    (packet_id,) = struct.unpack_from("!H", payload, pos)
                    pos += 2
                    while pos < len(payload):
                        filter_str, pos = self._read_string(payload, pos)
                        session.subscriptions.discard(filter_str)
                    writer.write(self._packet(11, struct.pack("!H", packet_id)))
                    await writer.drain()
                elif ptype == 12:  # PINGREQ
                    writer.write(self._packet(13))
                    await writer.drain()
                elif ptype == 14:  # DISCONNECT
                    break
                else:
                    # Unknown packet type — ignore to keep the connection alive.
                    logger.debug("embedded broker: ignoring packet type %s", ptype)
        except (asyncio.IncompleteReadError, ConnectionResetError, BrokenPipeError):
            pass
        except Exception:
            logger.exception("embedded broker connection error for %s", client_id)
        finally:
            self._sessions.pop(client_id, None)
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    async def _deliver(
        self,
        topic: str,
        body: bytes,
        qos: int,
        packet_id: int | None,
        sender: _Session,
    ) -> None:
        for other in list(self._sessions.values()):
            if not any(topic_matches(p, topic) for p in other.subscriptions):
                continue
            try:
                flags = 0x00
                variable = struct.pack("!H", len(topic)) + topic.encode("utf-8") + body
                if qos == 1 and packet_id is not None:
                    flags = 0x02
                    variable = struct.pack("!H", len(topic)) + topic.encode("utf-8")
                    variable += struct.pack("!H", packet_id) + body
                other.writer.write(self._packet(3, variable, flags=flags))
                await other.writer.drain()
            except Exception:
                logger.exception("embedded broker: failed to deliver to subscriber")
