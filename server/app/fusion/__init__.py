"""Fusion Engine — multi-modal identity fusion with adaptive weights.

Core algorithm for fusing face, gait, and BLE modalities into a unified
identity decision with explainable confidence scores.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("fusion")


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
    fusion_conf: float = 0.0
    modality_count: int = 0
    decision: str = "unknown"  # granted / denied / pending / unknown
    explain_text: str = ""
    timestamp: float = 0.0


# ── Face matching ─────────────────────────────────────────────────────


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
    """Match a face embedding against registered faces using cosine similarity.

    Args:
        embedding: 128-d face embedding from ESP32
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


# ── Gait matching ─────────────────────────────────────────────────────


def extract_gait_features(rle_data: str, width: int, height: int) -> dict:
    """Extract basic gait features from RLE-encoded silhouette.

    This is a simplified version. Full 3D HMR reconstruction is future work.

    Returns:
        dict with extracted spatial features
    """
    # Estimate silhouette area from RLE (simplified)
    # In a real system this would decode RLE → binary mask → contour → features
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
    """Match silhouette/gait features.

    Currently simplified — returns low confidence for non-face modalities.
    Full gait embedding matching is future work with HMR 3D reconstruction.

    Returns:
        ModalityResult with gait confidence
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


# ── BLE matching ──────────────────────────────────────────────────────


def rssi_to_proximity(rssi: float) -> float:
    """Convert BLE RSSI to a proximity score (0.0~1.0).

    RSSI ~ -30 → very close (1.0)
    RSSI ~ -50 → close (0.8)
    RSSI ~ -70 → medium (0.5)
    RSSI ~ -90 → far (0.2)
    RSSI < -100 → out of range (0.0)
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
    """Match BLE MAC address against registered persons.

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
            # BLE alone is not highly reliable — weight by proximity
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
    """Multi-modal identity fusion engine with adaptive weights.

    Fuses face, gait, and BLE modalities using adaptive weight allocation
    based on environmental conditions (light level, signal quality).
    """

    # Base weights for each modality
    BASE_WEIGHTS = {
        "face": 0.60,
        "gait": 0.20,
        "ble": 0.20,
    }

    # Light-based adjustment: face weight decreases in low light
    LIGHT_ADJUSTMENT = {
        "high": {"face": 1.0, "gait": 0.8, "ble": 0.6},  # light > 0.7
        "medium": {"face": 0.8, "gait": 1.0, "ble": 0.8},  # light 0.3~0.7
        "low": {"face": 0.4, "gait": 1.2, "ble": 1.2},  # light < 0.3
    }

    DECISION_THRESHOLD = 0.55  # minimum fusion confidence for "granted"
    HIGH_CONFIDENCE = 0.80  # considered high confidence
    TIMEOUT_SECONDS = 3.0  # max window for multi-modal collection

    def __init__(self):
        self._windows: dict[str, dict] = {}  # node_id → window state

    def _get_light_multiplier(self, light_level: float) -> dict:
        """Get light-based weight multipliers."""
        if light_level > 0.7:
            return self.LIGHT_ADJUSTMENT["high"]
        elif light_level > 0.3:
            return self.LIGHT_ADJUSTMENT["medium"]
        return self.LIGHT_ADJUSTMENT["low"]

    def _compute_adaptive_weights(self, light_level: float) -> dict[str, float]:
        """Compute adaptive weights based on light level."""
        multipliers = self._get_light_multiplier(light_level)
        weights = {}
        total = 0.0
        for modality in self.BASE_WEIGHTS:
            w = self.BASE_WEIGHTS[modality] * multipliers.get(modality, 1.0)
            weights[modality] = w
            total += w
        # Normalize
        if total > 0:
            for modality in weights:
                weights[modality] = round(weights[modality] / total, 4)
        return weights

    def update_window(self, node_id: str, modality: str, data: dict):
        """Update the sliding window for a node with new modality data."""
        now = time.time()
        if node_id not in self._windows:
            self._windows[node_id] = {
                "face": None,
                "gait": None,
                "ble": None,
                "light_level": 1.0,
                "last_update": now,
                "face_person_id": None,
                "face_person_name": "",
            }
        window = self._windows[node_id]
        window[modality] = data
        window["last_update"] = now

        # Extract light level from face data if available
        if modality == "face":
            window["light_level"] = data.get("light", 1.0)
            window["face_person_id"] = data.get("person_id")
            window["face_person_name"] = data.get("person_name", "")

    def get_window(self, node_id: str) -> Optional[dict]:
        """Get the current fused window state for a node."""
        return self._windows.get(node_id)

    def clear_window(self, node_id: str):
        """Clear the window after a decision."""
        self._windows.pop(node_id, None)

    def check_timeout(self, node_id: str) -> bool:
        """Check if the window has timed out."""
        window = self._windows.get(node_id)
        if not window:
            return False
        elapsed = time.time() - window["last_update"]
        return elapsed > self.TIMEOUT_SECONDS

    def fuse(self, node_id: str, light_level: float = 1.0) -> Optional[FusionResult]:
        """Run fusion on the current window state.

        Returns None if insufficient data, or a FusionResult.
        """
        window = self._windows.get(node_id)
        if not window:
            return None

        face_result: Optional[ModalityResult] = window.get("face")
        gait_result: Optional[ModalityResult] = window.get("gait")
        ble_result: Optional[ModalityResult] = window.get("ble")

        # Count available modalities
        modalities_present = sum(
            1 for m in [face_result, gait_result, ble_result] if m is not None
        )
        if modalities_present == 0:
            return None

        # Compute adaptive weights
        weights = self._compute_adaptive_weights(light_level)

        # Weighted fusion
        fusion_conf = 0.0
        person_votes: dict[int, float] = {}

        def add_vote(result: Optional[ModalityResult], weight: float):
            if result and result.matched and result.person_id:
                score = result.confidence * weight
                person_votes[result.person_id] = (
                    person_votes.get(result.person_id, 0) + score
                )
                nonlocal fusion_conf
                fusion_conf += score

        add_vote(face_result, weights["face"])
        add_vote(gait_result, weights["gait"])
        add_vote(ble_result, weights["ble"])

        # Find best person match
        best_person_id = None
        best_person_score = 0.0
        best_person_name = ""

        if person_votes:
            best_person_id = max(person_votes, key=person_votes.get)
            best_person_score = person_votes[best_person_id]
            best_person_name = window.get("face_person_name", "")
            if not best_person_name and face_result:
                best_person_name = face_result.person_name

        # Decision logic
        if best_person_id and fusion_conf >= self.DECISION_THRESHOLD:
            decision = "granted"
            explanation = (
                f"多模态融合确认 {best_person_name}"
                f"（融合置信度 {fusion_conf:.2f}）"
            )
        elif best_person_id and fusion_conf >= 0.3:
            decision = "pending"
            explanation = (
                f"融合置信度不足 ({fusion_conf:.2f})，等待更多模态数据"
            )
        else:
            decision = "denied"
            explanation = f"未识别到匹配人员（融合置信度 {fusion_conf:.2f}）"
            best_person_id = None

        # Add modality details
        parts = []
        if face_result and face_result.matched:
            parts.append(f"人脸{face_result.confidence:.2f}")
        if gait_result and gait_result.matched:
            parts.append(f"步态{gait_result.confidence:.2f}")
        if ble_result and ble_result.matched:
            parts.append(f"BLE{ble_result.confidence:.2f}")
        if parts:
            explanation += f"（{' + '.join(parts)}）"

        return FusionResult(
            person_id=best_person_id,
            person_name=best_person_name,
            face_conf=face_result.confidence if face_result else 0.0,
            gait_conf=gait_result.confidence if gait_result else 0.0,
            ble_conf=ble_result.confidence if ble_result else 0.0,
            fusion_conf=round(fusion_conf, 4),
            modality_count=modalities_present,
            decision=decision,
            explain_text=explanation,
            timestamp=time.time(),
        )


# Singleton
fusion_engine = FusionEngine()
