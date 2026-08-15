from __future__ import annotations

from typing import Any

from ..models import CreditState
from ..scenarios import Scenario


class Stage4RiskMixin:
    """Context builders for Stage 4 Risk Committee Agents (A10 - A12)."""

    @staticmethod
    def _context_a10(state: CreditState, s: Scenario) -> dict[str, Any]:
        return {"deal": state.deal_proposal, "assessment": state.credit_assessment, "reports": state.analyst_reports}

    @staticmethod
    def _context_a11(state: CreditState, s: Scenario) -> dict[str, Any]:
        return {
            "deal": state.deal_proposal,
            "assessment": state.credit_assessment,
            "financial": state.analyst_reports["financial_capacity"],
            "risk_turns": state.risk_debate,
        }

    @staticmethod
    def _context_a12(state: CreditState, s: Scenario) -> dict[str, Any]:
        return {
            "deal": state.deal_proposal,
            "assessment": state.credit_assessment,
            "policy": state.analyst_reports["policy"],
            "risk_turns": state.risk_debate,
        }
