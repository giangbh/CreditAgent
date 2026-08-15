from __future__ import annotations

from typing import Any, Optional


class BaseBankAdapter:
    """Base Adapter interface for external Bank & Enterprise systems."""

    system_code: str = "GENERIC_BANK"
    description: str = "Generic Bank System Adapter"

    def __init__(self, endpoint_url: Optional[str] = None, api_key: Optional[str] = None) -> None:
        self.endpoint_url = endpoint_url
        self.api_key = api_key

    def is_healthy(self) -> bool:
        """Check connection health to external bank gateway."""
        return True

    def query(self, action: str, params: dict[str, Any]) -> dict[str, Any]:
        """Perform query to bank backend."""
        raise NotImplementedError("Subclasses must implement query()")
