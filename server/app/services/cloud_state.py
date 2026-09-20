"""Process-local view of hub↔cloud link state.

The durable source of truth is ``hubs.cloud_link`` (updated by topology
heartbeats); this cache avoids a DB read on every edge message and also
allows a forced offline/online toggle for the degrade demo.
"""

from __future__ import annotations


class CloudState:
    def __init__(self) -> None:
        # hub_id -> "online" | "offline" | "unknown"; None => use default
        self._overrides: dict[str, str] = {}
        self._known: dict[str, str] = {}

    def update(self, hub_id: str, state: str) -> None:
        self._known[hub_id] = state

    def force(self, hub_id: str, state: str) -> None:
        self._overrides[hub_id] = state

    def clear_force(self, hub_id: str) -> None:
        self._overrides.pop(hub_id, None)

    def state(self, hub_id: str) -> str:
        if hub_id in self._overrides:
            return self._overrides[hub_id]
        return self._known.get(hub_id, "unknown")

    def is_offline(self, hub_id: str | None) -> bool:
        # "unknown" counts as connected for the demo: staging only starts
        # after an explicit offline signal.
        return bool(hub_id) and self.state(hub_id) == "offline"


cloud_state = CloudState()
