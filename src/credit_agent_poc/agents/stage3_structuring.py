from __future__ import annotations

from typing import Any, Callable

from ..models import CreditState
from ..scenarios import Scenario


class Stage3StructuringMixin:
    """Context builders for Stage 3 Deal Structuring Agent (A9)."""

    _call: Callable[..., dict[str, Any]]
    _data: Callable[[dict[str, Any]], dict[str, Any]]

    def _context_a9(self, state: CreditState, s: Scenario) -> dict[str, Any]:
        self._call("A9", state, s, "calculate_credit_capacity")
        self._call("A9", state, s, "stress_repayment_capacity")
        self._call("A9", state, s, "evaluate_policy_rule")
        self._call("A9", state, s, "resolve_approval_authority")
        amortization = self._data(
            self._call(
                "A9",
                state,
                s,
                "calculate_amortization",
                amount=state.credit_assessment.get("recommended_amount", 0),
                tenor_months=s.request["tenor_months"],
            )
        )
        pricing = self._data(self._call("A9", state, s, "resolve_pricing_band"))
        validation = self._data(self._call("A9", state, s, "validate_deal_structure"))
        return {
            "assessment": state.credit_assessment,
            "policy": state.analyst_reports["policy"],
            "cashflow": state.analyst_reports["cashflow"],
            "request": state.case_file["request"],
            "amortization": amortization,
            "pricing": pricing,
            "validation": validation,
        }
