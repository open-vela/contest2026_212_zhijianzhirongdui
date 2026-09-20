#!/usr/bin/env python3
"""Fusion engine tests: BLE+motion delivery profile + face/gait research.

Covers the 2026-09-20 scope revision: shipped firmware evidence is a BLE
beacon allowlist hit (primary) plus camera motion/presence (secondary);
face/gait fusion stays available as an explicitly labelled research/offline
profile (offline gait Rank-1 = 86.7% is a report-only claim).
"""

import sys
import time

sys.path.insert(0, "..")

import pytest  # noqa: E402

from app.fusion.fusion_engine import (  # noqa: E402
    DELIVERY_WEIGHTS,
    POLICY_DEGRADE_FACE,
    POLICY_EMPLOYEE_NORMAL,
    POLICY_TAILGATE,
    POLICY_UNKNOWN_DENY,
    POLICY_VISITOR_TEMP,
    FusionEngine,
)

NODE = "test-edge-fusion"


def _engine():
    return FusionEngine()


def _put(engine, node_id, modality, **data):
    engine.update_window(node_id, modality, data)


def _age(engine, node_id, seconds):
    w = engine.get_window(node_id)
    w["window_start"] = time.time() - seconds
    w["last_update"] = time.time() - seconds


# ── Delivery profile: BLE beacon + camera presence ────────────────────


def test_delivery_beacon_plus_motion_allows():
    e = _engine()
    _put(e, NODE, "ble", matched=True, person_id=1, person_name="张伟",
         confidence=0.9)
    _put(e, NODE, "motion", present=True, confidence=0.82)
    r = e.fuse(NODE)
    assert r.action == "allow"
    assert r.policy_id == POLICY_EMPLOYEE_NORMAL
    assert r.evidence_mode == "delivery"
    assert set(r.weights_used) == {"ble", "motion"}
    assert r.fusion_conf >= 0.65
    # Chinese explanation names both evidence channels.
    assert "BLE 信标" in r.explain_text and "在场轮廓" in r.explain_text
    envelope = r.as_decision_dict()
    assert set(envelope) == {"action", "policy_id", "explanation",
                             "confidence", "weights_used"}


def test_delivery_motion_only_is_pending_then_denies_on_timeout():
    e = _engine()
    _put(e, NODE, "motion", present=True, confidence=0.8)
    # No BLE scan yet: hold briefly for the scan result.
    r = e.fuse(NODE)
    assert r.decision == "pending"
    assert r.policy_id == POLICY_UNKNOWN_DENY
    # Whole window elapses with no beacon: hard default deny.
    _age(e, NODE, 4.0)
    r = e.fuse(NODE)
    assert r.action == "deny"
    assert r.policy_id == POLICY_UNKNOWN_DENY


def test_delivery_motion_with_empty_scan_denies_immediately():
    """The required demo case: 仅运动无信标 → UNKNOWN-DENY without waiting."""
    e = _engine()
    _put(e, NODE, "motion", present=True, confidence=0.8)
    _put(e, NODE, "ble", matched=False, confidence=0.05, mac="AA:BB:CC:00:00:01")
    r = e.fuse(NODE)
    assert r.action == "deny"
    assert r.policy_id == POLICY_UNKNOWN_DENY
    assert r.evidence_mode == "delivery"
    assert "拒绝通行" in r.explain_text


def test_delivery_beacon_without_motion_pending_then_denies():
    e = _engine()
    _put(e, NODE, "ble", matched=True, person_id=1, confidence=0.9)
    r = e.fuse(NODE)
    assert r.decision == "pending"  # credential seen, no one at the door yet
    _age(e, NODE, 4.0)
    r = e.fuse(NODE)
    assert r.action == "deny"
    assert r.policy_id == POLICY_UNKNOWN_DENY


def test_delivery_tailgate_is_alert():
    e = _engine()
    _put(e, NODE, "ble", matched=True, person_id=1, confidence=0.9)
    _put(e, NODE, "motion", present=True, confidence=0.85, tailgate=True)
    r = e.fuse(NODE)
    assert r.action == "alert"
    assert r.policy_id == POLICY_TAILGATE
    assert "尾随" in r.explain_text


def test_delivery_crowded_scene_shifts_weight_to_beacon():
    e = _engine()
    _put(e, NODE, "ble", matched=True, person_id=1, confidence=0.9)
    _put(e, NODE, "motion", present=True, confidence=0.8, crowd_count=4)
    r = e.fuse(NODE)
    assert r.scenario == "crowded"
    assert r.weights_used["ble"] == DELIVERY_WEIGHTS["crowded"]["ble"]
    assert r.action == "allow"


def test_delivery_visitor_requires_validity_window():
    e = _engine()
    _put(e, NODE, "ble", matched=True, person_id=2, person_name="访客",
         person_type="visitor", visitor_valid=True, confidence=0.9)
    _put(e, NODE, "motion", present=True, confidence=0.8)
    r = e.fuse(NODE)
    assert r.action == "allow"
    assert r.policy_id == POLICY_VISITOR_TEMP

    e2 = _engine()
    _put(e2, NODE + "v", "ble", matched=True, person_id=2,
         person_type="visitor", visitor_valid=False, confidence=0.9)
    _put(e2, NODE + "v", "motion", present=True, confidence=0.8)
    r = e2.fuse(NODE + "v")
    assert r.action == "deny"
    assert r.policy_id == POLICY_UNKNOWN_DENY


# ── Research / offline profile: face + gait + BLE ─────────────────────


def test_research_front_three_modalities_allows():
    e = _engine()
    _put(e, NODE, "face", matched=True, person_id=1, person_name="张伟",
         confidence=0.9, light=1.0)
    _put(e, NODE, "gait", matched=True, person_id=1, person_name="张伟",
         confidence=0.7)
    _put(e, NODE, "ble", matched=True, person_id=1, person_name="张伟",
         confidence=0.48)
    r = e.fuse(NODE)
    assert r.evidence_mode == "research"
    assert r.action == "allow"
    assert r.policy_id == POLICY_EMPLOYEE_NORMAL
    assert set(r.weights_used) == {"face", "gait", "ble"}
    assert "人脸" in r.explain_text


def test_research_low_face_confidence_degrades_policy():
    e = _engine()
    # Face visible but unreliable (<0.3) triggers DEGRADE-FACE-1.
    _put(e, NODE, "face", matched=False, person_id=None, confidence=0.2,
         light=1.0)
    _put(e, NODE, "gait", matched=True, person_id=1, person_name="张伟",
         confidence=0.82)
    _put(e, NODE, "ble", matched=True, person_id=1, person_name="张伟",
         confidence=0.48)
    r = e.fuse(NODE)
    assert r.degraded is True
    assert r.weights_used["face"] == 0.0
    assert r.action == "allow"
    assert r.policy_id == POLICY_DEGRADE_FACE


def test_research_back_prefers_gait():
    e = _engine()
    w = e.weights_for_scenario("back")
    assert w["gait"] > w["face"]


def test_research_two_unknown_modalities_deny():
    e = _engine()
    _put(e, NODE, "face", matched=False, confidence=0.1)
    _put(e, NODE, "ble", matched=False, confidence=0.05)
    r = e.fuse(NODE)
    assert r.action == "deny"
    assert r.policy_id == POLICY_UNKNOWN_DENY
