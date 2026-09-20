"""Fusion Engine — hub-side identity fusion with adaptive weights.

Two evidence profiles coexist (2026-09-20 scope revision):

* **Delivery profile (交付路径)** — what the shipped R528/ESP32-S3 firmware
  actually produces: BLE beacon identity (primary) + camera motion/silhouette
  presence (secondary). Dynamic weights ``w_ble / w_motion`` adapt to scene
  quality (crowded / low-light). Motion with NO beacon identity is a hard
  UNKNOWN-DENY — tailgating without a credential must never open the door.

* **Research / offline profile (研究/离线模式)** — the original three-modality
  face + gait/silhouette + BLE fusion with per-scenario weights
  (正面/侧身/背对/拥挤/低光). The offline gait Rank-1 = 86.7% result is a
  research claim reported in the competition report only; this code path is
  not exercised by shipped firmware.

Profile selection is automatic per fusion window: a window that never
received face or gait evidence runs the delivery profile; any face/gait
evidence activates the research profile.

Policy ids (template 3.2 policy set):

    EMPLOYEE-NORMAL / DEGRADE-FACE-1 / TAILGATE-DETECT /
    VISITOR-TEMP     / UNKNOWN-DENY

Policy precedence when several apply: DENY > ALERT > DEGRADE > ALLOW.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from app.config import settings

logger = logging.getLogger("fusion")

# Policy ids (template 3.2 policy set).
POLICY_EMPLOYEE_NORMAL = "EMPLOYEE-NORMAL"
POLICY_DEGRADE_FACE = "DEGRADE-FACE-1"
POLICY_TAILGATE = "TAILGATE-DETECT"
POLICY_VISITOR_TEMP = "VISITOR-TEMP"
POLICY_UNKNOWN_DENY = "UNKNOWN-DENY"

# Policy precedence: DENY > ALERT > DEGRADE > ALLOW.
POLICY_PRIORITY = {
    POLICY_UNKNOWN_DENY: 4,    # DENY
    POLICY_TAILGATE: 3,        # ALERT
    POLICY_DEGRADE_FACE: 2,    # DEGRADE
    POLICY_VISITOR_TEMP: 1,    # ALLOW (time-boxed)
    POLICY_EMPLOYEE_NORMAL: 0, # ALLOW
}

# Research profile: scenario → dynamic modality weights (w_face/w_gait/w_ble).
SCENARIO_WEIGHTS: dict[str, dict[str, float]] = {
    "front":    {"face": 0.60, "gait": 0.20, "ble": 0.20},  # 正面
    "side":     {"face": 0.35, "gait": 0.40, "ble": 0.25},  # 侧身
    "back":     {"face": 0.15, "gait": 0.55, "ble": 0.30},  # 背对
    "crowded":  {"face": 0.35, "gait": 0.30, "ble": 0.35},  # 拥挤
    "low_light": {"face": 0.30, "gait": 0.40, "ble": 0.30},  # 低光
}

# Delivery profile: BLE beacon identity (primary) + camera presence (secondary).
# In crowded/low-light scenes presence is less identity-informative, so BLE
# carries more of the decision.
DELIVERY_WEIGHTS: dict[str, dict[str, float]] = {
    "front":     {"ble": 0.75, "motion": 0.25},  # 默认
    "crowded":   {"ble": 0.85, "motion": 0.15},  # 拥挤：防尾随靠信标
    "low_light": {"ble": 0.80, "motion": 0.20},  # 低光：轮廓可信度下降
    "side":      {"ble": 0.75, "motion": 0.25},
    "back":      {"ble": 0.75, "motion": 0.25},
}

# Scenario selection precedence when several signals are present.
SCENARIO_PRECEDENCE = ("crowded", "low_light", "back", "side", "front")


@dataclass
class ModalityResult:
    """Result from a single modality matcher."""
    person_id: Optional[int] = None
    person_name: str = ""
    confidence: float = 0.0  # 0.0 ~ 1.0
    matched: bool = False


@dataclass
class FusionResult:
    """Final fused identity decision."""
    person_id: Optional[int] = None
    person_name: str = ""
    face_conf: float = 0.0
    gait_conf: float = 0.0
    ble_conf: float = 0.0
    motion_conf: float = 0.0
    fusion_conf: float = 0.0
    modality_count: int = 0
    # Legacy decision spelling kept for the events table / dashboard:
    # granted / denied / pending / unknown.
    decision: str = "unknown"
    explain_text: str = ""
    timestamp: float = 0.0
    # OPE-100 explainable policy output.
    action: str = "deny"  # allow / deny / alert
    policy_id: str = POLICY_UNKNOWN_DENY
    scenario: str = "front"
    # "delivery" (BLE+motion shipped firmware) or "research" (face/gait/ble).
    evidence_mode: str = "research"
    weights_used: dict = field(default_factory=dict)
    contributions: dict = field(default_factory=dict)
    degraded: bool = False
    name: str = ""

    def as_decision_dict(self) -> dict:
        """The template-3.3 decision envelope broadcast to clients/cloud."""
        return {
            "action": self.action,
            "policy_id": self.policy_id,
            "explanation": self.explain_text,
            "confidence": round(self.fusion_conf, 4),
            "weights_used": self.weights_used,
        }


# ── Face matching (research profile) ─────────────────────────────────


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


async def match_face(
    embedding: list[float],
    registered_faces: list[dict],
    threshold: float = 0.55,
) -> ModalityResult:
    """Match a face embedding against registered faces (research/offline).

    Args:
        embedding: 128-d face embedding
        registered_faces: list of {person_id, person_name, embedding}
        threshold: minimum similarity threshold

    Returns:
        ModalityResult with best match info
    """
    best_score = 0.0
    best_match: Optional[dict] = None

    for face in registered_faces:
        score = cosine_similarity(embedding, face.get("embedding", []))
        if score > best_score:
            best_score = score
            best_match = face

    if best_score >= threshold and best_match:
        return ModalityResult(
            person_id=best_match["person_id"],
            person_name=best_match.get("person_name", ""),
            confidence=round(best_score, 4),
            matched=True,
        )
    return ModalityResult(confidence=round(best_score, 4), matched=False)


# ── Gait matching (research profile; offline Rank-1 86.7%) ───────────


def extract_gait_features(rle_data: str, width: int, height: int) -> dict:
    """Extract basic gait features from RLE-encoded silhouette.

    This is a simplified version. Full 3D HMR reconstruction is future work.

    Returns:
        dict with extracted spatial features
    """
    feature = {
        "aspect_ratio": width / max(height, 1),
        "area_estimate": 0.0,
        "has_motion": True,
        "quality": 0.5,
    }
    return feature


async def match_gait(
    features: dict,
    reference_gait: Optional[dict] = None,
) -> ModalityResult:
    """Match silhouette/gait features (research/offline profile).

    Currently simplified — returns low confidence for non-face modalities.
    Full gait embedding matching is future work with HMR 3D reconstruction.
    """
    if not reference_gait:
        return ModalityResult(confidence=0.0, matched=False)

    # Simplified: gait is a supporting modality
    confidence = 0.3 if features.get("quality", 0) > 0.4 else 0.1
    return ModalityResult(
        person_id=reference_gait.get("person_id"),
        person_name=reference_gait.get("person_name", ""),
        confidence=confidence,
        matched=confidence > 0.25,
    )


# ── BLE matching (shared; primary evidence in the delivery profile) ───


def rssi_to_proximity(rssi: float) -> float:
    """Convert BLE RSSI to a proximity score (0.0~1.0).

    RSSI ~ -30 -> very close (1.0)
    RSSI ~ -50 -> close (0.8)
    RSSI ~ -70 -> medium (0.5)
    RSSI ~ -90 -> far (0.2)
    RSSI < -100 -> out of range (0.0)
    """
    if rssi >= -30:
        return 1.0
    if rssi <= -100:
        return 0.0
    return round((rssi + 100) / 70, 4)


async def match_ble(
    mac: str,
    rssi: float,
    registered_persons: list[dict],
) -> ModalityResult:
    """Match BLE MAC address against the registered allowlist.

    A MAC hit IS a beacon allowlist identity; the confidence is scaled by
    proximity so a distant beacon cannot alone reach the allow threshold.

    Args:
        mac: BLE MAC address from scan
        rssi: signal strength in dBm
        registered_persons: list of {person_id, person_name, ble_mac}

    Returns:
        ModalityResult with BLE-based confidence
    """
    proximity = rssi_to_proximity(rssi)

    for person in registered_persons:
        if person.get("ble_mac", "").upper() == mac.upper():
            confidence = proximity * 0.6
            return ModalityResult(
                person_id=person["person_id"],
                person_name=person.get("person_name", ""),
                confidence=round(confidence, 4),
                matched=proximity > 0.4,
            )

    return ModalityResult(confidence=round(proximity * 0.1, 4), matched=False)


# ── Fusion core ───────────────────────────────────────────────────────


class FusionEngine:
    """Hub-side identity fusion.

    Delivery profile: BLE beacon identity + camera motion/presence.
    Research profile: scenario-weighted face + gait + BLE, with a 0.65
    normal threshold / 0.55 degraded threshold; face confidence below 0.3
    triggers DEGRADE-FACE-1 and redistributes the face weight.
    """

    # Kept for backward compatibility with older callers/tests.
    BASE_WEIGHTS = SCENARIO_WEIGHTS["front"]
    LIGHT_ADJUSTMENT = {
        "high": {"face": 1.0, "gait": 0.8, "ble": 0.6},
        "medium": {"face": 0.8, "gait": 1.0, "ble": 0.8},
        "low": {"face": 0.4, "gait": 1.2, "ble": 1.2},
    }

    TIMEOUT_SECONDS = 3.0
    PENDING_FLOOR = 0.30

    def __init__(self):
        self._windows: dict[str, dict] = {}

    # ── Scenario / weight selection ───────────────────────────────────

    def detect_scenario(self, window: dict) -> str:
        """Pick one scenario from explicit hint and environmental signals."""
        hint = window.get("scenario_hint")
        if hint in SCENARIO_WEIGHTS:
            return hint
        crowd = window.get("crowd_count") or window.get("person_count")
        if crowd is not None:
            try:
                if int(crowd) >= 2:
                    return "crowded"
            except (TypeError, ValueError):
                pass
        light = float(window.get("light_level", 1.0) or 1.0)
        if light < 0.35:
            return "low_light"
        pose = (window.get("pose") or "front").lower()
        if pose in ("back", "rear"):
            return "back"
        if pose in ("side", "profile"):
            return "side"
        return "front"

    def _compute_adaptive_weights(self, light_level: float) -> dict[str, float]:
        """Legacy light-only weight table, retained for compatibility."""
        if light_level > 0.7:
            multipliers = self.LIGHT_ADJUSTMENT["high"]
        elif light_level > 0.3:
            multipliers = self.LIGHT_ADJUSTMENT["medium"]
        else:
            multipliers = self.LIGHT_ADJUSTMENT["low"]
        weights = {}
        total = 0.0
        for modality, base in self.BASE_WEIGHTS.items():
            w = base * multipliers.get(modality, 1.0)
            weights[modality] = w
            total += w
        if total > 0:
            weights = {m: round(w / total, 4) for m, w in weights.items()}
        return weights

    def weights_for_scenario(self, scenario: str) -> dict[str, float]:
        return dict(SCENARIO_WEIGHTS.get(scenario, SCENARIO_WEIGHTS["front"]))

    def delivery_weights_for_scenario(self, scenario: str) -> dict[str, float]:
        return dict(DELIVERY_WEIGHTS.get(scenario, DELIVERY_WEIGHTS["front"]))

    # ── Sliding window ────────────────────────────────────────────────

    def update_window(self, node_id: str, modality: str, data: dict | ModalityResult):
        """Update the sliding window for a node with new modality data.

        Accepts either a dict or ModalityResult object. Dict payloads may
        carry scenario context: light, pose, crowd_count/person_count,
        scenario_hint, tailgate. ``modality="motion"`` records camera
        presence evidence for the delivery profile:
        ``{present: bool, confidence: 0..1}``.
        """
        now = time.time()
        if node_id not in self._windows:
            self._windows[node_id] = {m: None for m in ("face", "gait", "ble", "motion")}
            self._windows[node_id]["light_level"] = 1.0
            self._windows[node_id]["last_update"] = now
            self._windows[node_id]["window_start"] = now
            self._windows[node_id]["face_person_id"] = None
            self._windows[node_id]["face_person_name"] = ""

        window = self._windows[node_id]

        if isinstance(data, ModalityResult):
            window[modality] = {
                "person_id": data.person_id,
                "person_name": data.person_name,
                "confidence": data.confidence,
                "matched": data.matched,
            }
        else:
            window[modality] = data
            if modality == "face":
                window["light_level"] = data.get("light", 1.0)
                window["face_person_id"] = data.get("person_id")
                window["face_person_name"] = data.get("person_name", "")
            if modality == "motion":
                window["light_level"] = data.get("light", window.get("light_level", 1.0))
            for ctx_key in ("pose", "crowd_count", "person_count", "scenario_hint"):
                if ctx_key in data and data[ctx_key] is not None:
                    window[ctx_key] = data[ctx_key]
            if data.get("light") is not None:
                window["light_level"] = data.get("light", 1.0)
            if data.get("tailgate"):
                window["tailgate"] = True

        window["last_update"] = now

    def get_window(self, node_id: str) -> Optional[dict]:
        return self._windows.get(node_id)

    def clear_window(self, node_id: str):
        self._windows.pop(node_id, None)

    def check_timeout(self, node_id: str) -> bool:
        window = self._windows.get(node_id)
        if not window:
            return False
        return (time.time() - window["last_update"]) > self.TIMEOUT_SECONDS

    def timed_out_nodes(self) -> list[str]:
        """Node ids whose evidence window has been stale past TIMEOUT_SECONDS."""
        now = time.time()
        return [
            nid for nid, w in self._windows.items()
            if (now - float(w.get("last_update", now))) > self.TIMEOUT_SECONDS
        ]

    # ── Fusion entry point ────────────────────────────────────────────

    def fuse(self, node_id: str, light_level: float | None = None) -> Optional[FusionResult]:
        """Run fusion on the current window state.

        Returns None if no evidence exists, otherwise a FusionResult
        carrying the policy id, action and Chinese explanation.
        """
        window = self._windows.get(node_id)
        if not window:
            return None

        if light_level is not None:
            window["light_level"] = light_level

        # Profile selection: face/gait evidence activates the research
        # profile; the shipped firmware path (BLE + camera presence) uses
        # the delivery profile.
        if window.get("face") is None and window.get("gait") is None:
            if window.get("ble") is None and window.get("motion") is None:
                return None
            return self._fuse_delivery(node_id, window)
        return self._fuse_research(node_id, window)

    # ── Delivery profile: BLE beacon identity + camera presence ───────

    def _fuse_delivery(self, node_id: str, window: dict) -> FusionResult:
        scenario = self.detect_scenario(window)
        weights = self.delivery_weights_for_scenario(scenario)

        ble_data: Optional[dict] = window.get("ble")
        motion_data: Optional[dict] = window.get("motion")
        ble_present = ble_data is not None
        motion_present = bool(motion_data and motion_data.get("present", False))
        motion_conf = float(motion_data.get("confidence", 0.0)) if motion_data else 0.0
        ble_conf = float(ble_data.get("confidence", 0.0)) if ble_data else 0.0
        # A matched beacon allowlist hit is the identity, even when the edge
        # only forwards "allowlist_hit=true" without a server-side person id
        # (shipped firmware case).
        ble_identity = bool(ble_data and ble_data.get("matched"))
        tailgate = bool(window.get("tailgate"))
        window_age = time.time() - float(window.get("window_start", time.time()))
        timed_out = window_age > self.TIMEOUT_SECONDS

        contributions = {"ble": 0.0, "motion": 0.0}
        person_id = None
        person_name = ""
        person_type = "employee"
        visitor_valid = False
        fusion_conf = 0.0

        if ble_identity:
            person_id = ble_data.get("person_id")
            person_name = ble_data.get("person_name", "")
            person_type = ble_data.get("person_type", "employee")
            visitor_valid = ble_data.get("visitor_valid")
            if visitor_valid is None:
                visitor_valid = person_type == "visitor"
            contributions["ble"] = round(ble_conf * weights["ble"], 4)
            fusion_conf += contributions["ble"]
        if motion_present:
            contributions["motion"] = round(motion_conf * weights["motion"], 4)
            fusion_conf += contributions["motion"]
        fusion_conf = round(min(fusion_conf, 1.0), 4)

        modalities_present = int(ble_present) + int(motion_present)

        # Policy selection (DENY > ALERT > DEGRADE > ALLOW).
        if tailgate:
            action, policy_id, decision = "alert", POLICY_TAILGATE, "denied"
        elif ble_identity:
            # An allowlisted beacon proved identity; camera presence is the
            # second factor confirming the credential holder is at the door.
            if person_type == "visitor":
                if not visitor_valid:
                    action, policy_id, decision = "deny", POLICY_UNKNOWN_DENY, "denied"
                elif motion_present and fusion_conf >= settings.FUSION_THRESHOLD_NORMAL:
                    action, policy_id, decision = "allow", POLICY_VISITOR_TEMP, "granted"
                elif timed_out:
                    action, policy_id, decision = "deny", POLICY_UNKNOWN_DENY, "denied"
                else:
                    action, policy_id, decision = "pending", POLICY_VISITOR_TEMP, "pending"
            elif not motion_present:
                # Credential seen, presence not yet confirmed: hold the
                # window open, then default-deny on timeout.
                if timed_out:
                    action, policy_id, decision = "deny", POLICY_UNKNOWN_DENY, "denied"
                else:
                    action, policy_id, decision = "pending", POLICY_EMPLOYEE_NORMAL, "pending"
            elif fusion_conf >= settings.FUSION_THRESHOLD_NORMAL:
                action, policy_id, decision = "allow", POLICY_EMPLOYEE_NORMAL, "granted"
            else:
                # Both evidence types present but too weak (far beacon, ...).
                action, policy_id, decision = "deny", POLICY_UNKNOWN_DENY, "denied"
        elif motion_present:
            # Someone is at the door with no allowlisted beacon. A scan that
            # already came back empty (or a full-window wait) finalizes the
            # default deny; otherwise hold briefly for the scan result.
            if ble_present or timed_out:
                action, policy_id, decision = "deny", POLICY_UNKNOWN_DENY, "denied"
            else:
                action, policy_id, decision = "pending", POLICY_UNKNOWN_DENY, "pending"
        else:
            # Only an unmatched BLE scan (or no usable evidence): wait for
            # camera presence, deny on timeout.
            if modalities_present == 0:
                return None
            if timed_out:
                action, policy_id, decision = "deny", POLICY_UNKNOWN_DENY, "denied"
            else:
                action, policy_id, decision = "pending", POLICY_UNKNOWN_DENY, "pending"

        if person_name:
            name = person_name
        elif ble_identity:
            # On-device allowlist hits often carry no server-side name.
            name = "已授权信标"
        else:
            name = "未知人员"
        explanation = self._explain_delivery(
            name=name,
            fusion_conf=fusion_conf,
            contributions=contributions,
            ble_present=ble_present,
            motion_present=motion_present,
            policy_id=policy_id,
            action=action,
            tailgate=tailgate,
        )

        return FusionResult(
            person_id=person_id,
            person_name=person_name,
            name=name,
            ble_conf=round(ble_conf, 4),
            motion_conf=round(motion_conf if motion_present else 0.0, 4),
            fusion_conf=fusion_conf,
            modality_count=modalities_present,
            decision=decision,
            explain_text=explanation,
            timestamp=time.time(),
            action=action,
            policy_id=policy_id,
            scenario=scenario,
            evidence_mode="delivery",
            weights_used=weights,
            contributions=contributions,
            degraded=False,
        )

    @staticmethod
    def _explain_delivery(
        *,
        name: str,
        fusion_conf: float,
        contributions: dict,
        ble_present: bool,
        motion_present: bool,
        policy_id: str,
        action: str,
        tailgate: bool,
    ) -> str:
        """Delivery-profile explanation: BLE 信标 + 在场轮廓."""
        parts = []
        if ble_present:
            parts.append(f"BLE 信标 {round(contributions.get('ble', 0.0) * 100)}%")
        if motion_present:
            parts.append(f"在场轮廓 {round(contributions.get('motion', 0.0) * 100)}%")
        detail = "+".join(parts) if parts else "无有效证据"
        text = f"{name or '未知人员'}，融合分 {fusion_conf * 100:.1f}%（{detail}），策略:{policy_id}"
        if tailgate:
            text += "（检测到尾随，转安保复核）"
        elif action == "pending":
            text += "（证据未齐，等待另一模态确认）"
        elif action == "deny":
            if motion_present and not ble_present:
                text += "（仅检测到人员在场、无允许信标，默认拒绝）"
            else:
                text += "（拒绝通行）"
        elif action == "allow":
            text += "（信标身份+在场双证据一致，放行）"
        return text

    # ── Research profile: face + gait + BLE (offline) ─────────────────

    def _fuse_research(self, node_id: str, window: dict) -> FusionResult:
        face_data: Optional[dict] = window.get("face")
        gait_data: Optional[dict] = window.get("gait")
        ble_data: Optional[dict] = window.get("ble")
        modalities = {"face": face_data, "gait": gait_data, "ble": ble_data}
        modalities_present = sum(1 for m in modalities.values() if m is not None)
        if modalities_present == 0:
            return None

        scenario = self.detect_scenario(window)
        base_weights = self.weights_for_scenario(scenario)

        # Quality-aware weight allocation:
        # - unseen modalities keep their reserved weight (they may still
        #   arrive within the fusion window), so a single early modality
        #   cannot reach the threshold by itself;
        # - a present-but-unreliable face (conf < 0.3) triggers
        #   DEGRADE-FACE-1: its weight is redistributed to gait/ble in
        #   proportion to their scenario base weights;
        # - matched-modality votes below use the resulting weights.
        face_raw_conf = float(face_data.get("confidence", 0)) if face_data else 0.0
        degraded = bool(face_data) and face_raw_conf < settings.FUSION_FACE_DEGRADE_BELOW
        weights = dict(base_weights)
        if degraded and weights["face"] > 0:
            spare = weights["face"]
            weights["face"] = 0.0
            keepers = ("gait", "ble")
            keeper_mass = sum(base_weights[m] for m in keepers)
            if keeper_mass:
                for m in keepers:
                    weights[m] = round(base_weights[m] + spare * base_weights[m] / keeper_mass, 4)

        # Per-person weighted votes; contributions track the winning person.
        person_votes: dict[int, dict] = {}
        for modality, data in modalities.items():
            if not data or not data.get("matched") or not data.get("person_id"):
                continue
            pid = data["person_id"]
            score = float(data.get("confidence", 0)) * weights[modality]
            entry = person_votes.setdefault(pid, {
                "score": 0.0,
                "name": data.get("person_name", ""),
                "person_type": data.get("person_type", "employee"),
                "visitor_valid": data.get("visitor_valid"),
                "contributions": {"face": 0.0, "gait": 0.0, "ble": 0.0},
            })
            entry["score"] += score
            entry["contributions"][modality] = round(score, 4)
            if data.get("person_name"):
                entry["name"] = data["person_name"]
            if data.get("person_type"):
                entry["person_type"] = data["person_type"]
            if data.get("visitor_valid") is not None:
                entry["visitor_valid"] = data["visitor_valid"]

        best_person_id = None
        best = None
        if person_votes:
            best_person_id = max(person_votes, key=lambda pid: person_votes[pid]["score"])
            best = person_votes[best_person_id]
        fusion_conf = round(best["score"], 4) if best else 0.0
        best_name = best["name"] if best else (window.get("face_person_name", "") or "未知人员")

        face_conf = float(face_data.get("confidence", 0)) if face_data else 0.0
        gait_conf = float(gait_data.get("confidence", 0)) if gait_data else 0.0
        ble_conf = float(ble_data.get("confidence", 0)) if ble_data else 0.0

        # Face degrade trigger: a visible but unreliable face channel.
        degraded = bool(face_data) and face_conf < settings.FUSION_FACE_DEGRADE_BELOW
        threshold = (
            settings.FUSION_THRESHOLD_DEGRADED if degraded
            else settings.FUSION_THRESHOLD_NORMAL
        )

        tailgate = bool(window.get("tailgate"))
        person_type = (best or {}).get("person_type", "employee")
        visitor_valid = self._visitor_valid(best)

        window_age = time.time() - float(window.get("window_start", time.time()))
        action, policy_id, decision = self._select_policy(
            has_winner=best is not None,
            fusion_conf=fusion_conf,
            threshold=threshold,
            degraded=degraded,
            tailgate=tailgate,
            person_type=person_type,
            visitor_valid=visitor_valid,
            modality_count=modalities_present,
            window_age=window_age,
        )

        contributions = best["contributions"] if best else {"face": 0.0, "gait": 0.0, "ble": 0.0}
        explanation = self._explain(
            name=best_name if best else "未知人员",
            fusion_conf=fusion_conf,
            contributions=contributions,
            modalities=modalities,
            policy_id=policy_id,
            action=action,
            scenario=scenario,
            degraded=degraded,
            tailgate=tailgate,
        )

        return FusionResult(
            person_id=best_person_id,
            person_name=best_name,
            name=best_name or "未知人员",
            face_conf=round(face_conf, 4),
            gait_conf=round(gait_conf, 4),
            ble_conf=round(ble_conf, 4),
            fusion_conf=fusion_conf,
            modality_count=modalities_present,
            decision=decision,
            explain_text=explanation,
            timestamp=time.time(),
            action=action,
            policy_id=policy_id,
            scenario=scenario,
            evidence_mode="research",
            weights_used=weights,
            contributions=contributions,
            degraded=degraded,
        )

    @staticmethod
    def _visitor_valid(winner_entry: dict | None) -> bool:
        """A VISITOR-TEMP match only allows inside its validity window."""
        if not winner_entry or winner_entry.get("person_type") != "visitor":
            return False
        valid = winner_entry.get("visitor_valid")
        if valid is None:
            # Default to the common demo case: an appointment row checked the
            # window before handing the evidence to fusion.
            return True
        return bool(valid)

    def _select_policy(
        self,
        *,
        has_winner: bool,
        fusion_conf: float,
        threshold: float,
        degraded: bool,
        tailgate: bool,
        person_type: str,
        visitor_valid: bool,
        modality_count: int,
        window_age: float = 0.0,
    ) -> tuple[str, str, str]:
        """Return (action, policy_id, legacy decision) — research profile.

        Precedence: DENY > ALERT > DEGRADE > ALLOW. The window needs at
        least two modalities (or an explicit tailgate) before a hard deny
        is final, so evidence arriving a few hundred ms apart can still fuse.
        Past TIMEOUT_SECONDS the pending state is finalized as a deny.
        """
        # ALERT class: tailgating detected — never auto-open, raise alert.
        if tailgate:
            return "alert", POLICY_TAILGATE, "denied"
        timed_out = window_age > self.TIMEOUT_SECONDS
        if not has_winner or fusion_conf < self.PENDING_FLOOR:
            if modality_count >= 2 or timed_out:
                return "deny", POLICY_UNKNOWN_DENY, "denied"
            return "pending", POLICY_UNKNOWN_DENY, "pending"
        if person_type == "visitor":
            if not visitor_valid:
                return "deny", POLICY_UNKNOWN_DENY, "denied"
            if fusion_conf >= threshold:
                return "allow", POLICY_VISITOR_TEMP, "granted"
            return "pending", POLICY_VISITOR_TEMP, "pending"
        if fusion_conf >= threshold:
            if degraded:
                return "allow", POLICY_DEGRADE_FACE, "granted"
            return "allow", POLICY_EMPLOYEE_NORMAL, "granted"
        # Evidence exists but is insufficient — wait for more modalities.
        return "pending", POLICY_EMPLOYEE_NORMAL, "pending"

    @staticmethod
    def _explain(
        *,
        name: str,
        fusion_conf: float,
        contributions: dict,
        modalities: dict,
        policy_id: str,
        action: str,
        scenario: str,
        degraded: bool,
        tailgate: bool,
    ) -> str:
        """Research profile. Format: {name}，融合分 xx.x%（人脸 x%+轮廓 x%+BLE x%），策略:XXX."""
        labels = [("face", "人脸"), ("gait", "轮廓"), ("ble", "BLE")]
        parts = [
            f"{label} {round(contributions.get(key, 0.0) * 100)}%"
            for key, label in labels
            if modalities.get(key) is not None
        ]
        detail = "+".join(parts) if parts else "无有效模态"
        text = f"{name or '未知人员'}，融合分 {fusion_conf * 100:.1f}%（{detail}），策略:{policy_id}"
        if tailgate:
            text += "（检测到尾随，转安保复核）"
        elif degraded and action == "allow":
            text += "（人脸通道降级，已按轮廓+BLE 放行）"
        elif action == "pending":
            text += "（置信度不足，等待更多模态）"
        elif action == "deny":
            text += "（拒绝通行）"
        return text


# Singleton
fusion_engine = FusionEngine()
