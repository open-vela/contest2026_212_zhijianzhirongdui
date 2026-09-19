"""Pluggable cloud delivery transports for the demo outbox."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from app.config import settings


@dataclass(slots=True)
class DeliveryResult:
    delivered: bool
    status_code: int | None = None
    receipt: dict[str, Any] = field(default_factory=dict)
    error_code: str | None = None
    error_message: str | None = None


class CloudTransport(Protocol):
    mode: str
    provider: str

    async def deliver(self, envelope: dict[str, Any]) -> DeliveryResult: ...


class DisabledCloudTransport:
    mode = "disabled"
    provider = "disabled"

    async def deliver(self, envelope: dict[str, Any]) -> DeliveryResult:
        return DeliveryResult(
            delivered=False,
            error_code="CLOUD_DISABLED",
            error_message="Cloud delivery is disabled; item remains in the local outbox.",
        )


class MockCloudTransport:
    """Deterministic local transport; it never claims public-cloud delivery."""

    mode = "mock"
    provider = "local_mock"

    async def deliver(self, envelope: dict[str, Any]) -> DeliveryResult:
        return DeliveryResult(
            delivered=True,
            status_code=200,
            receipt={
                "transport": "local_mock",
                "accepted": True,
                "idempotency_key": envelope["idempotency_key"],
                "note": "Local mock acknowledgement; no public cloud was contacted.",
            },
        )


class MisconfiguredHttpCloudTransport:
    """HTTP mode without an endpoint: explicit failure, never silent disablement."""

    mode = "http"
    provider = "generic_http"

    async def deliver(self, envelope: dict[str, Any]) -> DeliveryResult:
        return DeliveryResult(
            delivered=False,
            error_code="HTTP_ENDPOINT_MISSING",
            error_message="DEMO_CLOUD_ENDPOINT is required when DEMO_CLOUD_MODE=http.",
        )


class HttpCloudTransport:
    mode = "http"
    provider = "generic_http"

    def __init__(
        self,
        endpoint: str,
        timeout_seconds: float,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.endpoint = endpoint
        self.timeout_seconds = timeout_seconds
        self._transport = transport

    async def deliver(self, envelope: dict[str, Any]) -> DeliveryResult:
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds,
                transport=self._transport,
                follow_redirects=False,
            ) as client:
                response = await client.post(
                    self.endpoint,
                    json=envelope,
                    headers={"Idempotency-Key": envelope["idempotency_key"]},
                )
            try:
                body = response.json()
            except ValueError:
                body = {"body": response.text[:1024]}
            if 200 <= response.status_code < 300:
                return DeliveryResult(True, response.status_code, body if isinstance(body, dict) else {"data": body})
            return DeliveryResult(
                False,
                response.status_code,
                error_code=f"HTTP_{response.status_code}",
                error_message=str(body)[:1024],
            )
        except httpx.TimeoutException as exc:
            return DeliveryResult(False, error_code="HTTP_TIMEOUT", error_message=str(exc) or "Cloud request timed out")
        except httpx.HTTPError as exc:
            return DeliveryResult(False, error_code="HTTP_TRANSPORT_ERROR", error_message=str(exc)[:1024])


def configured_cloud_transport() -> CloudTransport:
    mode = settings.DEMO_CLOUD_MODE
    if mode == "mock":
        return MockCloudTransport()
    if mode == "http":
        if settings.DEMO_CLOUD_ENDPOINT:
            return HttpCloudTransport(settings.DEMO_CLOUD_ENDPOINT, settings.DEMO_CLOUD_TIMEOUT_SECONDS)
        return MisconfiguredHttpCloudTransport()
    return DisabledCloudTransport()
