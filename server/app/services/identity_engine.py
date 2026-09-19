"""Identity Engine — orchestrates MQTT data → fusion → DB → WebSocket.

Receives raw modality data from MQTT topics, runs it through the
fusion engine, persists results, and broadcasts decisions via WebSocket.
"""

import asyncio
import logging
import time
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.fusion.fusion_engine import (
    FusionResult,
    FusionEngine,
    ModalityResult,
    extract_gait_features,
    match_ble,
    match_face,
    match_gait,
)
from app.models.database import async_session_factory
from app.models.models import Device, Event, Face, Person
from app.services.ws_manager import ws_manager

logger = logging.getLogger("identity")


class IdentityEngine:
    """Orchestrator for the identity recognition pipeline.

    Flow: MQTT → modality matching → fusion → Event DB → WebSocket broadcast

    Also supports camera-based enrollment: the REST API registers a pending
    capture for a node, and the next face embedding arriving from that node
    over MQTT is stored as the person's reference embedding (no server-side
    model needed — the ESP32 extracts the embedding, the server only stores
    and compares).
    """

    # Max seconds to wait for an embedding after an enrollment capture is requested.
    ENROLL_TIMEOUT_SECONDS = 30.0

    def __init__(self, fusion_engine: FusionEngine):
        self.fusion = fusion_engine
        # node_id -> {person_id, person_name, tenant_id, future, created_at}
        self._enrollment_captures: dict[str, dict] = {}

    # ── Enrollment capture (camera-based, no server model) ───────────

    def request_enrollment(
        self,
        node_id: str,
        person_id: int,
        person_name: str,
        tenant_id: int,
    ) -> asyncio.Future:
        """Register a pending enrollment capture.

        The next face embedding from `node_id` arriving via MQTT will be
        stored as `person_id`'s reference embedding. Returns a Future that
        resolves with {face_id, embedding_len} on capture.
        """
        loop = asyncio.get_event_loop()
        future = loop.create_future()
        self._enrollment_captures[node_id] = {
            "person_id": person_id,
            "person_name": person_name,
            "tenant_id": tenant_id,
            "future": future,
            "created_at": time.time(),
        }
        logger.info(f"[Enroll] Awaiting capture from node={node_id} "
                    f"person={person_id}({person_name})")
        return future

    def cancel_enrollment(self, node_id: str):
        cap = self._enrollment_captures.pop(node_id, None)
        if cap and not cap["future"].done():
            cap["future"].cancel()

    def _expire_stale_enrollments(self):
        """Drop enrollment captures that have waited longer than the timeout."""
        now = time.time()
        for node_id in list(self._enrollment_captures.keys()):
            cap = self._enrollment_captures[node_id]
            if now - cap["created_at"] > self.ENROLL_TIMEOUT_SECONDS + 5:
                if not cap["future"].done():
                    cap["future"].cancel()
                self._enrollment_captures.pop(node_id, None)
                logger.warning(f"[Enroll] Expired stale capture for node={node_id}")

    # ── Face handler ──────────────────────────────────────────────────

    async def on_face(self, topic: str, payload: dict):
        """Handle incoming face embedding from MQTT."""
        node_id = payload.get("node_id", topic.split("/")[2] if "/" in topic else "unknown")
        embedding = payload.get("embedding") or payload.get("emb", [])
        light = payload.get("light", 1.0)
        timestamp = payload.get("timestamp") or payload.get("ts")

        logger.info(f"[Face] node={node_id} light={light:.2f} emb_len={len(embedding)}")

        if not embedding or len(embedding) < 64:
            logger.warning(f"[Face] Invalid embedding from {node_id}")
            return

        self._expire_stale_enrollments()

        # ── Enrollment capture takes priority over matching ──
        cap = self._enrollment_captures.pop(node_id, None)
        if cap and not cap["future"].done():
            try:
                async with async_session_factory() as db:
                    face = Face(
                        person_id=cap["person_id"],
                        embedding=embedding,
                        image_url="",
                        quality_score=round(float(light), 4),
                    )
                    db.add(face)
                    await db.commit()
                    await db.refresh(face)
                    face_id = face.id
                logger.info(f"[Enroll] Captured embedding for person={cap['person_id']} "
                            f"({cap['person_name']}) from node={node_id} face_id={face_id}")
                cap["future"].set_result({
                    "status": "captured",
                    "face_id": face_id,
                    "embedding_len": len(embedding),
                    "node_id": node_id,
                })
                await ws_manager.broadcast("enrollment", {
                    "person_id": cap["person_id"],
                    "person_name": cap["person_name"],
                    "node_id": node_id,
                    "face_id": face_id,
                    "status": "captured",
                })
            except Exception as e:
                logger.error(f"[Enroll] Failed to store capture: {e}")
                if not cap["future"].done():
                    cap["future"].set_exception(e)
            return  # do not proceed to matching during enrollment

        # Query registered faces from DB.
        # NOTE: must eager-load Face.person — accessing the relationship lazily
        # in an async context raises MissingGreenlet (the original bug that
        # silently broke the whole recognition pipeline).
        async with async_session_factory() as db:
            result = await db.execute(
                select(Face)
                .options(selectinload(Face.person))
                .join(Person)
                .where(Person.is_active == True)  # noqa: E712
            )
            faces = result.scalars().all()

            registered = [
                {
                    "person_id": f.person_id,
                    "person_name": f.person.name if f.person else "",
                    "embedding": f.embedding,
                }
                for f in faces
                if f.embedding and f.person
            ]

            # Also get persons with BLE MACs for cross-reference
            persons_result = await db.execute(
                select(Person).where(
                    Person.tenant_id == 1,
                    Person.is_active == True,  # noqa: E712
                    Person.ble_mac != "",
                )
            )
            persons = persons_result.scalars().all()

        # Match face
        face_result = await match_face(embedding, registered)
        if not face_result.matched:
            logger.info(f"[Face] No match from {node_id} (best={face_result.confidence:.4f})")
            # Still update window with negative result for gait/BLE to help
            self.fusion.update_window(node_id, "face", ModalityResult(
                confidence=face_result.confidence, matched=False))

        # Store matched person info in window
        face_data = {
            "person_id": face_result.person_id,
            "person_name": face_result.person_name,
            "confidence": face_result.confidence,
            "matched": face_result.matched,
            "light": light,
            "embedding": embedding,
        }
        self.fusion.update_window(node_id, "face", face_data)

        # Try fusion
        await self._try_fusion(node_id, db=None)

    # ── Silhouette handler ────────────────────────────────────────────

    async def on_silhouette(self, topic: str, payload: dict):
        """Handle incoming silhouette/gait data from MQTT."""
        node_id = payload.get("node_id", topic.split("/")[2] if "/" in topic else "unknown")
        rle = payload.get("rle", "")
        width = payload.get("width", 80)
        height = payload.get("height", 60)

        # Extract basic gait features
        features = extract_gait_features(rle, width, height)

        # Simplified gait matching (future: full gait embedding)
        gait_result = await match_gait(features)
        gait_data = {
            "person_id": gait_result.person_id,
            "person_name": gait_result.person_name,
            "confidence": gait_result.confidence,
            "matched": gait_result.matched,
            "features": features,
        }
        self.fusion.update_window(node_id, "gait", gait_data)
        logger.info(f"[Gait] node={node_id} conf={gait_result.confidence:.4f}")

        await self._try_fusion(node_id, db=None)

    # ── BLE handler ───────────────────────────────────────────────────

    async def on_ble(self, topic: str, payload: dict):
        """Handle incoming BLE scan data from MQTT."""
        node_id = payload.get("node_id", topic.split("/")[2] if "/" in topic else "unknown")
        devices = payload.get("devices", [payload])  # single or batch

        async with async_session_factory() as db:
            persons_result = await db.execute(
                select(Person).where(
                    Person.tenant_id == 1,
                    Person.is_active == True,  # noqa: E712
                    Person.ble_mac != "",
                )
            )
            registered_persons = [
                {"person_id": p.id, "person_name": p.name, "ble_mac": p.ble_mac}
                for p in persons_result.scalars().all()
            ]

        # Process each BLE device in the scan
        for dev in (devices if isinstance(devices, list) else [devices]):
            mac = dev.get("mac", "")
            rssi = dev.get("rssi", -100)
            if not mac:
                continue

            ble_result = await match_ble(mac, rssi, registered_persons)
            ble_data = {
                "person_id": ble_result.person_id,
                "person_name": ble_result.person_name,
                "confidence": ble_result.confidence,
                "matched": ble_result.matched,
                "mac": mac,
                "rssi": rssi,
            }

            # Only update window if we have a match or it's the first BLE data
            if ble_result.matched:
                self.fusion.update_window(node_id, "ble", ble_data)
                logger.info(f"[BLE] node={node_id} mac={mac} rssi={rssi} "
                            f"match={ble_result.person_name} conf={ble_result.confidence:.4f}")
                await self._try_fusion(node_id, db=None)

    # ── Status handler ────────────────────────────────────────────────

    async def on_status(self, topic: str, payload: dict):
        """Handle device heartbeat/status from MQTT."""
        node_id = payload.get("node_id", topic.split("/")[2] if "/" in topic else "unknown")
        timestamp = payload.get("ts") or payload.get("timestamp")

        logger.info(f"[Status] node={node_id}")

        async with async_session_factory() as db:
            # Find or create device
            device = (
                await db.execute(
                    select(Device).where(Device.node_id == node_id)
                )
            ).scalar_one_or_none()

            if not device:
                device = Device(
                    tenant_id=1,
                    node_id=node_id,
                    name=f"Node-{node_id}",
                    location="",
                    device_type="camera",
                    is_online=True,
                )
                db.add(device)
                logger.info(f"[Device] Auto-registered new device: {node_id}")
            else:
                device.is_online = True

            device.last_seen = datetime.utcnow()
            if isinstance(timestamp, (int, float)):
                device.last_seen = datetime.fromtimestamp(timestamp)

            await db.commit()

        # Broadcast device status via WebSocket
        await ws_manager.broadcast("device_status", {
            "node_id": node_id,
            "is_online": True,
            "last_seen": datetime.utcnow().isoformat(),
        })

    # ── Fusion trigger ────────────────────────────────────────────────

    async def _try_fusion(self, node_id: str, db: AsyncSession | None):
        """Attempt fusion decision and persist result."""
        window = self.fusion.get_window(node_id)
        if not window:
            return

        # Check if we have at least one positive modality or timeout
        face = window.get("face")
        light_level = window.get("light_level", 1.0)

        result = self.fusion.fuse(node_id, light_level=light_level)
        if not result:
            return

        logger.info(f"[Fusion] node={node_id} decision={result.decision} "
                     f"conf={result.fusion_conf:.4f} person={result.person_name}")

        # Persist to database
        async with async_session_factory() as db_session:
            # Find device
            device = (
                await db_session.execute(
                    select(Device).where(Device.node_id == node_id)
                )
            ).scalar_one_or_none()

            event = Event(
                tenant_id=1,
                person_id=result.person_id,
                person_name=result.person_name,
                device_id=device.id if device else None,
                node_id=node_id,
                face_conf=result.face_conf,
                gait_conf=result.gait_conf,
                ble_conf=result.ble_conf,
                fusion_conf=result.fusion_conf,
                modality_count=result.modality_count,
                decision=result.decision,
                explain_text=result.explain_text,
                is_alert=(result.decision == "denied"),
                created_at=datetime.utcnow(),
            )
            db_session.add(event)
            await db_session.commit()
            event_id = event.id

            # Also publish to MQTT vela/decision
            from app.services.mqtt_client import mqtt_client
            from app.config import settings
            mqtt_client.publish(f"{settings.MQTT_TOPIC_PREFIX}/decision", {
                "person_id": result.person_id,
                "action": result.decision,
                "explanation": result.explain_text,
                "confidence": result.fusion_conf,
            })

            # Publish alert if denied
            if result.decision == "denied" and result.fusion_conf > 0.3:
                mqtt_client.publish(f"{settings.MQTT_TOPIC_PREFIX}/alert", {
                    "level": "warning",
                    "type": "unauthorized_access",
                    "message": f"未授权通行: {node_id} (conf={result.fusion_conf:.2f})",
                    "timestamp": datetime.utcnow().isoformat(),
                })
                from app.models.models import Alert
                alert = Alert(
                    tenant_id=1,
                    level="warning",
                    type="unauthorized_access",
                    title=f"未授权通行检测",
                    message=f"节点 {node_id} 检测到未授权人员（置信度 {result.fusion_conf:.2f}）",
                    related_event_id=event_id,
                )
                db_session.add(alert)
                await db_session.commit()

        # Broadcast via WebSocket
        await ws_manager.broadcast("recognition", {
            "id": event_id,
            "person_id": result.person_id,
            "person_name": result.person_name or "未知",
            "node_id": node_id,
            "face_conf": result.face_conf,
            "gait_conf": result.gait_conf,
            "ble_conf": result.ble_conf,
            "fusion_conf": result.fusion_conf,
            "modality_count": result.modality_count,
            "decision": result.decision,
            "explain_text": result.explain_text,
        })

        # Clear window for next recognition cycle
        self.fusion.clear_window(node_id)


# Singleton
identity_engine = IdentityEngine(
    fusion_engine=__import__("app.fusion.fusion_engine", fromlist=["fusion_engine"]).fusion_engine
)
