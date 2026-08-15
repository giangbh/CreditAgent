from __future__ import annotations

from typing import Any

from ..models import CreditState
from ..scenarios import Scenario


class Stage2ChallengeMixin:
    """Context builders for Stage 2 Credit Challenge Agents (A6 - A8)."""

    @staticmethod
    def _context_a6(state: CreditState, s: Scenario) -> dict[str, Any]:
        return {"reports": state.analyst_reports, "data_quality": state.data_quality}

    @staticmethod
    def _context_a7(state: CreditState, s: Scenario) -> dict[str, Any]:
        return {"reports": state.analyst_reports, "data_quality": state.data_quality, "debate": state.credit_debate}

    @staticmethod
    def _context_a8(state: CreditState, s: Scenario) -> dict[str, Any]:
        return {"reports": state.analyst_reports, "data_quality": state.data_quality, "debate": state.credit_debate}
