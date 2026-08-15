from __future__ import annotations

from typing import Any

from ..models import CreditState
from ..scenarios import Scenario


class Stage5OpinionMixin:
    """Context builder for Stage 5 Co-Approval Manager Agent (A13)."""

    @staticmethod
    def _context_a13(state: CreditState, s: Scenario) -> dict[str, Any]:
        return {
            "reports": state.analyst_reports,
            "data_quality": state.data_quality,
            "assessment": state.credit_assessment,
            "deal": state.deal_proposal,
            "risk_turns": state.risk_debate,
        }
