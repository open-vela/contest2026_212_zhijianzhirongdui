"""MiMo cloud model access surface (template 3.3).

Two enhancement calls are provisioned around the hub decision:

- ``infer_intent``      — guess the subject's intent from the scene context
                          (正常通行 / 尾随 / 徘徊 / 访客拜访 ...)
- ``explain_decision``  — rewrite/augment the Chinese access explanation

Authentication uses the VELAMESH_MIMO_API_KEY environment variable ONLY; no
key is ever stored in the repository. When the key is absent (the current
demo default) every call is served by a deterministic local mock and
``mode`` reports "mock" — reports must not claim cloud inference.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger("mimo")


class MimoClient:
    @property
    def mode(self) -> str:
        return "cloud" if settings.MIMO_API_KEY else "mock"

    @property
    def configured(self) -> bool:
        return bool(settings.MIMO_API_KEY)

    # ── Public API ────────────────────────────────────────────────────

    async def infer_intent(self, context: dict[str, Any]) -> dict[str, Any]:
        if self.mode == "mock":
            return self._mock_intent(context)
        return await self._chat(
            system="你是门禁场景意图识别器，只输出 JSON。",
            user=f"根据以下门禁上下文判断人员意图，输出 JSON {{\"intent\": str, \"confidence\": 0..1}}：{context}",
            fallback=self._mock_intent(context),
        )

    async def explain_decision(
        self, decision: dict[str, Any], context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        if self.mode == "mock":
            return self._mock_explain(decision)
        return await self._chat(
            system="你是可解释访问控制助手，用一句简体中文增强解释，只输出 JSON。",
            user=(
                f"决策 {decision}，上下文 {context or {}}；输出 JSON："
                "{\"enhanced_explanation\": str, \"reason_codes\": [str]}"
            ),
            fallback=self._mock_explain(decision),
        )

    # ── Cloud transport ───────────────────────────────────────────────

    async def _chat(self, system: str, user: str, fallback: dict[str, Any]) -> dict[str, Any]:
        url = f"{settings.MIMO_BASE_URL.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {settings.MIMO_API_KEY}",
            "Content-Type": "application/json",
        }
        body = {
            "model": settings.MIMO_MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.2,
        }
        try:
            async with httpx.AsyncClient(timeout=settings.MIMO_TIMEOUT_SECONDS) as client:
                response = await client.post(url, json=body, headers=headers)
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            import json

            parsed = json.loads(content)
            if isinstance(parsed, dict):
                parsed.setdefault("mode", "cloud")
                return parsed
        except Exception as exc:  # network, auth, schema — never block the door
            logger.warning("MiMo cloud call failed, using mock: %s", exc)
        return fallback

    # ── Deterministic local mock ──────────────────────────────────────

    @staticmethod
    def _mock_intent(context: dict[str, Any]) -> dict[str, Any]:
        if context.get("tailgate"):
            return {"intent": "尾随进入", "confidence": 0.82, "mode": "mock"}
        if context.get("person_type") == "visitor":
            return {"intent": "访客拜访", "confidence": 0.75, "mode": "mock"}
        if context.get("scenario") == "back":
            return {"intent": "离开通行", "confidence": 0.7, "mode": "mock"}
        return {"intent": "正常通行", "confidence": 0.9, "mode": "mock"}

    @staticmethod
    def _mock_explain(decision: dict[str, Any]) -> dict[str, Any]:
        policy = decision.get("policy_id", "")
        reason_codes = {
            "EMPLOYEE-NORMAL": ["FUSED_MATCH", "THRESHOLD_PASS"],
            "DEGRADE-FACE-1": ["FACE_LOW_CONFIDENCE", "GAIT_BLE_FALLBACK"],
            "TAILGATE-DETECT": ["TAILGATE_SUSPECTED", "MANUAL_REVIEW"],
            "VISITOR-TEMP": ["VISITOR_APPROVED", "TIMEBOXED_PASS"],
            "UNKNOWN-DENY": ["NO_IDENTITY", "DEFAULT_DENY"],
        }.get(policy, ["POLICY_MATCH"])
        return {
            "enhanced_explanation": decision.get("explanation", ""),
            "reason_codes": reason_codes,
            "mode": "mock",
        }


mimo_client = MimoClient()
