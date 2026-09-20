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
    rssi_to_proximity,
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
    # How often stale pending windows are finalized.
    REAP_INTERVAL_SECONDS = 1.0

    def __init__(self, fusion_engine: FusionEngine):
        self.fusion = fusion_engine
        # node_id -> {person_id, person_name, tenant_id, future, created_at}
        self._enrollment_captures: dict[str, dict] = {}
        self._reaper_task: asyncio.Task | None = None

    # ── Pending-window reaper ─────────────────────────────────────────

    def start_reaper(self) -> None:
        """Finalize windows stuck in "pending" past the fusion timeout."""
        if self._reaper_task is None or self._reaper_task.done():
            self._reaper_task = asyncio.create_task(self._reap_loop())

    async def stop_reaper(self) -> None:
        task = self._reaper_task
        self._reaper_task = None
        if task and not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass

    async def _reap_loop(self) -> None:
        while True:
            await asyncio.sleep(self.REAP_INTERVAL_SECONDS)
            try:
                for node_id in self.fusion.timed_out_nodes():
                    await self._try_fusion(node_id, db=None, force=True)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("[Fusion] pending-window reaper error")

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

    async def on_face_score(
        self,
        node_id: str,
        *,
        score: float,
        person_id: int | None,
        person_name: str = "",
        person_type: str = "employee",
        context: dict | None = None,
    ):
        """Feed a face confidence already computed on the edge/R528.

        Used by simulated edge nodes and by hub-side face inference; the
        embedding path remains :meth:`on_face` for ESP32-S3 vectors.
        """
        context = context or {}
        matched = bool(person_id) and score >= 0.3
        face_data = {
            "person_id": person_id if matched else None,
            "person_name": person_name,
            "confidence": round(max(0.0, min(1.0, score)), 4),
            "matched": matched,
            "light": context.get("light", 1.0),
            "person_type": person_type,
        }
        for ctx_key in ("pose", "crowd_count", "person_count", "scenario_hint", "tailgate"):
            if ctx_key in context:
                face_data[ctx_key] = context[ctx_key]
        self.fusion.update_window(node_id, "face", face_data)
        logger.info("[Face-score] node=%s person=%s conf=%.4f", node_id, person_name, score)
        await self._try_fusion(node_id, db=None)

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
            "person_type": payload.get("person_type", "employee"),
        }
        # Scenario context advertised by the edge (optional).
        for ctx_key in ("pose", "crowd_count", "person_count", "scenario_hint", "tailgate"):
            if ctx_key in payload:
                face_data[ctx_key] = payload[ctx_key]
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
            "person_type": payload.get("person_type", "employee"),
        }
        for ctx_key in ("pose", "crowd_count", "person_count", "scenario_hint", "tailgate"):
            if ctx_key in payload:
                gait_data[ctx_key] = payload[ctx_key]
        self.fusion.update_window(node_id, "gait", gait_data)
        logger.info(f"[Gait] node={node_id} conf={gait_result.confidence:.4f}")

        await self._try_fusion(node_id, db=None)

    async def on_gait_score(
        self,
        node_id: str,
        *,
        score: float,
        person_id: int | None,
        person_name: str = "",
        person_type: str = "employee",
        context: dict | None = None,
    ):
        """Feed a gait/silhouette score already computed on the R528/edge."""
        context = context or {}
        matched = bool(person_id) and score >= 0.3
        gait_data = {
            "person_id": person_id if matched else None,
            "person_name": person_name,
            "confidence": round(max(0.0, min(1.0, score)), 4),
            "matched": matched,
            "features": context.get("features", {}),
            "person_type": person_type,
        }
        for ctx_key in ("pose", "crowd_count", "person_count", "scenario_hint", "tailgate", "light"):
            if ctx_key in context:
                gait_data[ctx_key] = context[ctx_key]
        self.fusion.update_window(node_id, "gait", gait_data)
        logger.info("[Gait-score] node=%s person=%s conf=%.4f", node_id, person_name, score)
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
            # Shipped firmware performs the allowlist check on-device and
            # reports allowlist_hit without a server-side person id: the
            # beacon is the identity in the BLE+motion delivery profile.
            edge_allowlist_hit = bool(dev.get("allowlist_hit") or dev.get("matched"))
            if not ble_result.matched and edge_allowlist_hit:
                proximity = rssi_to_proximity(float(rssi))
                # The allowlist match itself is authoritative identity
                # evidence; RSSI is only a proximity gate (must be at the
                # door, not across the building).
                default_score = 0.9 if proximity > 0.4 else 0.45
                ble_data = {
                    "person_id": dev.get("person_id"),
                    "person_name": dev.get("person_name", ""),
                    "confidence": round(float(dev.get("score", default_score)), 4),
                    "matched": True,
                    "mac": mac,
                    "rssi": rssi,
                    "person_type": dev.get("person_type", "employee"),
                }
            else:
                ble_data = {
                    "person_id": ble_result.person_id,
                    "person_name": ble_result.person_name,
                    "confidence": ble_result.confidence,
                    "matched": ble_result.matched,
                    "mac": mac,
                    "rssi": rssi,
                    "person_type": (dev.get("person_type", "employee")),
                }
            if dev.get("visitor_valid") is not None:
                ble_data["visitor_valid"] = dev.get("visitor_valid")

            # In the delivery profile every scan is evidence: an unmatched
            # scan means "no credential found at the door", so motion + an
            # unmatched scan denies without waiting for the fusion timeout.
            # In the research profile unmatched BLE is ignored, preserving
            # the face/gait sliding-window behaviour.
            existing = self.fusion.get_window(node_id) or {}
            in_delivery_profile = not (existing.get("face") or existing.get("gait"))
            if ble_data["matched"] or in_delivery_profile:
                self.fusion.update_window(node_id, "ble", ble_data)
            if ble_data["matched"]:
                logger.info(f"[BLE] node={node_id} mac={mac} rssi={rssi} "
                            f"match={ble_data['person_name'] or 'allowlist-hit'} "
                            f"conf={ble_data['confidence']:.4f}")
            await self._try_fusion(node_id, db=None)

    async def on_ble_score(
        self,
        node_id: str,
        *,
        score: float,
        person_id: int | None,
        person_name: str = "",
        mac: str = "",
        person_type: str = "employee",
        context: dict | None = None,
    ):
        """Feed a BLE identity score already computed on the edge/hub."""
        context = context or {}
        # An edge-reported allowlist hit is an identity even when the server
        # person table has no matching row (on-device allowlist firmware).
        matched = bool(person_id) and score > 0.0
        if context.get("edge_matched") or context.get("matched"):
            matched = score > 0.0
        ble_data = {
            "person_id": person_id if matched else None,
            "person_name": person_name,
            "confidence": round(max(0.0, min(1.0, score)), 4),
            "matched": matched,
            "mac": mac,
            "rssi": context.get("rssi", -100),
            "person_type": person_type,
        }
        if context.get("visitor_valid") is not None:
            ble_data["visitor_valid"] = context["visitor_valid"]
        self.fusion.update_window(node_id, "ble", ble_data)
        logger.info("[BLE-score] node=%s person=%s conf=%.4f", node_id, person_name, score)
        await self._try_fusion(node_id, db=None)

    # ── Motion / presence handler (delivery profile) ─────────────────

    async def on_motion(self, node_id: str, payload: dict):
        """Feed camera motion/presence evidence (BLE+motion delivery path).

        Accepted payload keys: ``present`` (default true when a ``motion``
        confidence or ``motion_detected`` flag is supplied) and
        ``confidence``/``motion`` (0..1 presence confidence). Context keys
        (light/pose/crowd/scenario_hint/tailgate) are forwarded to the
        fusion window for dynamic-weight selection.
        """
        if "present" in payload:
            present = bool(payload.get("present"))
        elif "motion_detected" in payload:
            present = bool(payload.get("motion_detected"))
        else:
            present = True
        confidence = payload.get("confidence", payload.get("motion", 0.8 if present else 0.0))
        try:
            confidence = max(0.0, min(1.0, float(confidence)))
        except (TypeError, ValueError):
            confidence = 0.8 if present else 0.0
        motion_data = {"present": present, "confidence": confidence}
        for ctx_key in ("light", "pose", "crowd_count", "person_count",
                        "scenario_hint", "tailgate"):
            if ctx_key in payload and payload[ctx_key] is not None:
                motion_data[ctx_key] = payload[ctx_key]
        self.fusion.update_window(node_id, "motion", motion_data)
        logger.info("[Motion] node=%s present=%s conf=%.2f", node_id, present, confidence)
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

    async def _try_fusion(
        self, node_id: str, db: AsyncSession | None, *, force: bool = False
    ):
        """Attempt fusion decision and persist result.

        ``force=True`` is used by the stale-window reaper: windows that stay
        "pending" past the fusion timeout are re-fused (the engine then
        finalizes them as a deny) and cleared.
        """
        window = self.fusion.get_window(node_id)
        if not window:
            return

        # Check if we have at least one positive modality or timeout
        light_level = window.get("light_level", 1.0)

        result = self.fusion.fuse(node_id, light_level=light_level)
        if not result:
            return
        if result.decision == "pending" and not force:
            # Fresh pending: fall through to the pending branch below.
            pass
        elif result.decision == "pending" and force:
            # Stale window: age the window so the engine finalizes it.
            window["window_start"] = time.time() - (self.fusion.TIMEOUT_SECONDS + 1)
            result = self.fusion.fuse(node_id, light_level=light_level)
            if not result or result.decision == "pending":
                # Nothing more can arrive for this evidence set.
                self.fusion.clear_window(node_id)
                return

        logger.info(f"[Fusion] node={node_id} policy={result.policy_id} "
                     f"action={result.action} conf={result.fusion_conf:.4f} "
                     f"person={result.person_name} scenario={result.scenario}")

        # "pending" means evidence exists but has not reached threshold: keep
        # the sliding window open so later modalities complete the decision.
        if result.decision == "pending":
            logger.info("[Fusion] node=%s pending (%.2f), awaiting more modalities",
                        node_id, result.fusion_conf)
            await ws_manager.broadcast("decision_pending", {
                "node_id": node_id,
                "fusion_conf": result.fusion_conf,
                "explanation": result.explain_text,
                "policy_id": result.policy_id,
            })
            return

        from app.services.topology import topology
        hub_id = await topology.hub_for_edge(node_id)

        # Best-effort MiMo explanation/intent enhancement (mock when no key).
        mimo_note = None
        try:
            from app.services.mimo_client import mimo_client
            mimo_note = await asyncio.wait_for(
                mimo_client.explain_decision(result.as_decision_dict(), {
                    "scenario": result.scenario,
                    "node_id": node_id,
                }),
                timeout=3.0,
            )
        except Exception as e:
            logger.debug("MiMo enhancement skipped: %s", e)

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
                hub_id=hub_id,
                face_conf=result.face_conf,
                gait_conf=result.gait_conf,
                ble_conf=result.ble_conf,
                motion_conf=result.motion_conf,
                fusion_conf=result.fusion_conf,
                modality_count=result.modality_count,
                decision=result.decision,
                policy_id=result.policy_id,
                scenario=result.scenario,
                evidence_mode=result.evidence_mode,
                weights_json=result.weights_used,
                explain_text=result.explain_text,
                raw_data_json={"mimo": mimo_note} if mimo_note else {},
                is_alert=(result.action in ("deny", "alert")),
                created_at=datetime.utcnow(),
            )
            db_session.add(event)
            await db_session.commit()
            event_id = event.id

            # Also publish to MQTT (legacy vela/decision + new hub contract)
            from app.services.mqtt_client import mqtt_client
            from app.config import settings
            decision_envelope = {
                "node_id": node_id,
                "hub_id": hub_id,
                "person_id": result.person_id,
                "person_name": result.person_name or "未知",
                **result.as_decision_dict(),
                "scenario": result.scenario,
                "evidence_mode": result.evidence_mode,
                "contributions": result.contributions,
                "event_id": event_id,
                "ts": datetime.utcnow().isoformat() + "Z",
            }
            mqtt_client.publish(f"{settings.MQTT_TOPIC_PREFIX}/decision", decision_envelope)
            mqtt_client.publish(
                f"{settings.MQTT_EDGE_TOPIC_PREFIX}/{node_id}/decision",
                decision_envelope,
            )

            # Publish alert if denied / tailgate
            if result.action in ("deny", "alert") and result.fusion_conf > 0.3:
                alert_type = (
                    "tailgate_detected" if result.policy_id == "TAILGATE-DETECT"
                    else "unauthorized_access"
                )
                alert_title = (
                    "尾随通行检测" if alert_type == "tailgate_detected"
                    else "未授权通行检测"
                )
                mqtt_client.publish(f"{settings.MQTT_TOPIC_PREFIX}/alert", {
                    "level": "warning",
                    "type": alert_type,
                    "policy_id": result.policy_id,
                    "message": f"{alert_title}: {node_id} (conf={result.fusion_conf:.2f})",
                    "timestamp": datetime.utcnow().isoformat(),
                })
                from app.models.models import Alert
                alert = Alert(
                    tenant_id=1,
                    level="warning",
                    type=alert_type,
                    title=alert_title,
                    message=f"节点 {node_id} 策略 {result.policy_id}（融合分 {result.fusion_conf:.2f}）",
                    related_event_id=event_id,
                )
                db_session.add(alert)
                await db_session.commit()

        # Broadcast via WebSocket (legacy "recognition" + hub decision shape)
        await ws_manager.broadcast("recognition", {
            "id": event_id,
            "person_id": result.person_id,
            "person_name": result.person_name or "未知",
            "node_id": node_id,
            "hub_id": hub_id,
            "face_conf": result.face_conf,
            "gait_conf": result.gait_conf,
            "ble_conf": result.ble_conf,
            "motion_conf": result.motion_conf,
            "fusion_conf": result.fusion_conf,
            "modality_count": result.modality_count,
            "decision": result.decision,
            "action": result.action,
            "policy_id": result.policy_id,
            "scenario": result.scenario,
            "evidence_mode": result.evidence_mode,
            "weights_used": result.weights_used,
            "contributions": result.contributions,
            "mimo": mimo_note,
            **result.as_decision_dict(),
            "explain_text": result.explain_text,
        })

        # Clear window for next recognition cycle
        self.fusion.clear_window(node_id)


# Singleton
identity_engine = IdentityEngine(
    fusion_engine=__import__("app.fusion.fusion_engine", fromlist=["fusion_engine"]).fusion_engine
)
