from __future__ import annotations

from typing import Any

from ..model import ModelAdapter
from ..models import CreditState, StatePatch, StateValidationError
from ..prompts import prompt_for
from ..scenarios import Scenario
from ..tools import ToolGateway

from .base import AgentExecution
from .registry import AGENT_NAMES
from .stage1_evidence import Stage1EvidenceMixin
from .stage2_challenge import Stage2ChallengeMixin
from .stage3_structuring import Stage3StructuringMixin
from .stage4_risk import Stage4RiskMixin
from .stage5_opinion import Stage5OpinionMixin


class AgentRuntime(
    Stage1EvidenceMixin,
    Stage2ChallengeMixin,
    Stage3StructuringMixin,
    Stage4RiskMixin,
    Stage5OpinionMixin,
):
    """Runtime environment executing agent prompts, calling tools, and producing state patches."""

    def __init__(self, model: ModelAdapter, tools: ToolGateway) -> None:
        self.model = model
        self.tools = tools

    def run(self, node_id: str, state: CreditState, scenario: Scenario) -> AgentExecution:
        if node_id not in AGENT_NAMES:
            raise StateValidationError(f"unknown agent node: {node_id}")
        context = getattr(self, f"_context_{node_id.lower()}")(state, scenario)
        prompt = prompt_for(node_id)
        output = self.model.generate(node_id, prompt, context)
        self._validate_output(node_id, output)
        patches = self._patches(node_id, state, output)
        return AgentExecution(
            node_id=node_id,
            agent_name=AGENT_NAMES[node_id],
            model_name=self.model.name,
            prompt=prompt,
            context=context,
            output=output,
            patches=patches,
        )

    @staticmethod
    def _data(response: dict[str, Any]) -> dict[str, Any]:
        return response.get("data", {}) if response.get("status") == "SUCCESS" else {}

    def _call(self, node: str, state: CreditState, scenario: Scenario, name: str, **arguments: Any) -> dict[str, Any]:
        return self.tools.call(node, state, scenario, name, arguments)

    @staticmethod
    def _validate_output(node_id: str, output: dict[str, Any]) -> None:
        if not isinstance(output, dict) or not output:
            raise StateValidationError(f"{node_id} returned an empty or invalid object")
        if node_id == "A13":
            valid = {"APPROVE_WITH_CONDITIONS", "ESCALATE_TO_CRO_RISK", "REJECT_INSUFFICIENT_EVIDENCE"}
            if output.get("status") != "DRAFT" or output.get("decision") not in valid:
                raise StateValidationError("A13 must return a DRAFT opinion with a supported decision")

    @staticmethod
    def _patches(node_id: str, state: CreditState, output: dict[str, Any]) -> list[StatePatch]:
        mapping: dict[str, list[tuple[str, str, str]]] = {
            "A1": [
                ("case_file", "case_file", "SET"),
                ("evidence_catalog", "evidence_catalog", "SET"),
                ("data_quality", "data_quality", "SET"),
            ],
            "A2": [("analyst_reports.cashflow", "", "SET")],
            "A3": [("analyst_reports.transaction_integrity", "", "SET")],
            "A4": [("analyst_reports.financial_capacity", "", "SET")],
            "A5": [("analyst_reports.policy", "", "SET")],
            "A6": [("credit_debate", "", "APPEND")],
            "A7": [("credit_debate", "", "APPEND")],
            "A8": [("credit_assessment", "", "SET")],
            "A9": [("deal_proposal", "", "SET")],
            "A10": [("risk_debate", "", "APPEND")],
            "A11": [("risk_debate", "", "APPEND")],
            "A12": [("risk_debate", "", "APPEND")],
            "A13": [("coapproval_opinion", "", "SET")],
        }
        patches = []
        for path, output_key, operation in mapping[node_id]:
            value = output[output_key] if output_key else output
            patches.append(
                StatePatch(
                    node_id=node_id,
                    path=path,
                    value=value,
                    operation=operation,
                    base_state_version=state.state_version,
                )
            )
        return patches


__all__ = ["AGENT_NAMES", "AgentExecution", "AgentRuntime"]
