from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..models import StatePatch


@dataclass
class AgentExecution:
    node_id: str
    agent_name: str
    model_name: str
    prompt: str
    context: dict[str, Any]
    output: dict[str, Any]
    patches: list[StatePatch]
