from __future__ import annotations

import json
import os
import urllib.request
from abc import ABC, abstractmethod
from typing import Any


class ModelAdapter(ABC):
    name = "abstract"

    @abstractmethod
    def generate(self, node_id: str, system_prompt: str, context: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError


class ScenarioModel(ModelAdapter):
    """Reproducible model double. It exercises the same agent boundaries without a remote LLM."""

    name = "scenario-model-v1"

    def generate(self, node_id: str, system_prompt: str, context: dict[str, Any]) -> dict[str, Any]:
        handler = getattr(self, f"_{node_id.lower()}")
        return handler(context)

    @staticmethod
    def _a1(c: dict[str, Any]) -> dict[str, Any]:
        completeness = c["completeness"]
        statement = c["statement"]
        missing = completeness.get("missing", [])
        status = "SUFFICIENT" if not missing else "INSUFFICIENT"
        return {
            "case_file": {
                "borrower": c["fields"]["borrower"],
                "request": c["fields"]["request"],
                "declared_revenue": c["fields"]["declared_revenue"],
                "transaction_artifact_ref": statement["artifact_ref"],
                "statement_months": statement["statement_months"],
            },
            "evidence_catalog": [
                {"evidence_id": "EVD-APPLICATION", "source": "application", "status": "VERIFIED"},
                {"evidence_id": "EVD-STATEMENT", "source": "bank_statement", "status": "VERIFIED"},
            ],
            "data_quality": {
                "overall": status,
                "missing": missing,
                "critical_gap": bool(missing),
                "human_review_required": bool(missing),
            },
        }

    @staticmethod
    def _a2(c: dict[str, Any]) -> dict[str, Any]:
        if c.get("tool_error"):
            return {
                "status": "PARTIAL",
                "rating": "UNKNOWN",
                "findings": ["cashflow_metrics_unavailable"],
                "data_gaps": ["deterministic_cashflow_backend_failed"],
                "evidence_refs": [],
            }
        metrics = c["metrics"]
        anomalies = c["anomalies"]
        rating = "CAUTION" if metrics["inflow_concentration"] >= 0.45 else "PASS"
        return {
            "status": "COMPLETE",
            "rating": rating,
            "observed_inflow": metrics["observed_inflow"],
            "inflow_concentration": metrics["inflow_concentration"],
            "coverage_months": metrics["coverage_months"],
            "findings": anomalies["anomalies"],
            "metric_id": metrics["metric_id"],
            "evidence_refs": [anomalies["evidence_id"]],
        }

    @staticmethod
    def _a3(c: dict[str, Any]) -> dict[str, Any]:
        cycles = c["cycles"]
        score = cycles["cycle_score"]
        return {
            "status": "COMPLETE",
            "rating": "CRITICAL" if score >= 0.8 else "PASS",
            "cycle_score": score,
            "cycle_ids": cycles["cycle_ids"],
            "related_party_coverage": c["graph"]["related_party_coverage"],
            "finding": "pattern_consistent_with_circular_funds" if score >= 0.8 else "no_material_cycle_detected",
            "evidence_refs": [cycles["evidence_id"]],
        }

    @staticmethod
    def _a4(c: dict[str, Any]) -> dict[str, Any]:
        capacity = c["capacity"]
        return {
            "status": "COMPLETE",
            "rating": "PASS" if capacity["primary_repayment_viable"] else "FAIL",
            "dscr": capacity["dscr"],
            "supported_amount": capacity["supported_amount"],
            "primary_repayment_viable": capacity["primary_repayment_viable"],
            "revenue_match_ratio": c["revenue"]["match_ratio"],
            "stressed_dscr": c["stress"]["stressed_dscr"],
            "calculation_refs": [capacity["calculation_ref"], c["stress"]["calculation_ref"]],
        }

    @staticmethod
    def _a5(c: dict[str, Any]) -> dict[str, Any]:
        rule = c["rule"]
        return {
            "status": "COMPLETE",
            "disposition": rule["disposition"],
            "rule_id": rule["rule_id"],
            "policy_citation_id": rule["policy_citation_id"],
            "citation_valid": c["citation"]["valid"],
            "authority": c["authority"]["authority"],
            "escalation_required": c["authority"]["escalation_required"] or rule["disposition"] == "MANDATORY_ESCALATION",
        }

    @staticmethod
    def _a6(c: dict[str, Any]) -> dict[str, Any]:
        financial = c["reports"]["financial_capacity"]
        thesis = "supportable_with_controls" if financial["primary_repayment_viable"] else "not_currently_supportable"
        return {
            "speaker": "CREDIT_ADVOCATE",
            "claim_id": "CLAIM-ADV-1",
            "thesis": thesis,
            "evidence_refs": financial.get("calculation_refs", []),
            "concessions": [] if thesis.startswith("supportable") else ["primary_repayment_not_demonstrated"],
        }

    @staticmethod
    def _a7(c: dict[str, Any]) -> dict[str, Any]:
        reports = c["reports"]
        challenges = []
        if reports["cashflow"]["rating"] in {"CAUTION", "UNKNOWN"}:
            challenges.append("cashflow_quality_or_coverage")
        if reports["transaction_integrity"]["rating"] == "CRITICAL":
            challenges.append("circular_funds_pattern")
        if not reports["financial_capacity"]["primary_repayment_viable"]:
            challenges.append("weak_primary_repayment")
        if reports["policy"]["escalation_required"]:
            challenges.append("mandatory_policy_escalation")
        return {
            "speaker": "RISK_CHALLENGER",
            "claim_id": "CLAIM-RISK-1",
            "challenges_claim_id": "CLAIM-ADV-1",
            "challenges": challenges or ["monitoring_conditions_must_be_enforceable"],
            "evidence_refs": ["CLAIM-ADV-1"],
        }

    @staticmethod
    def _a8(c: dict[str, Any]) -> dict[str, Any]:
        reports = c["reports"]
        if reports["cashflow"]["status"] == "PARTIAL" or c["data_quality"].get("critical_gap"):
            rating = "HOLD_FOR_INFO"
        elif not reports["financial_capacity"]["primary_repayment_viable"]:
            rating = "REJECT"
        elif reports["transaction_integrity"]["rating"] == "CRITICAL" or reports["policy"]["escalation_required"]:
            rating = "OVERWEIGHT_CAUTION"
        else:
            rating = "APPROVE"
        return {
            "rating": rating,
            "primary_repayment_source": "operating_cashflow",
            "accepted_claims": ["CLAIM-ADV-1"] if rating == "APPROVE" else [],
            "unresolved_risks": c["debate"][-1].get("challenges", []),
            "recommended_amount": reports["financial_capacity"].get("supported_amount", 0),
        }

    @staticmethod
    def _a9(c: dict[str, Any]) -> dict[str, Any]:
        assessment = c["assessment"]
        if assessment["rating"] in {"REJECT", "HOLD_FOR_INFO"}:
            action = "DECLINE"
        elif c["policy"]["escalation_required"] or not c["validation"]["valid"]:
            action = "ESCALATE"
        else:
            action = "PROPOSE"
        conditions = []
        if c["cashflow"]["rating"] == "CAUTION":
            conditions.append(
                {
                    "condition_id": "COND-CONCENTRATION",
                    "statement": "Monthly customer-concentration monitoring",
                    "owner_role": "CREDIT_MONITORING",
                    "due_point": "AFTER_DRAWDOWN",
                    "verification_method": "monthly_cashflow_metric",
                    "failure_consequence": "REVIEW",
                }
            )
        return {
            "action": action,
            "amount": min(c["request"]["amount"], assessment.get("recommended_amount", 0)),
            "tenor_months": c["request"]["tenor_months"],
            "pricing_band": c["pricing"]["pricing_band"],
            "conditions": conditions,
            "validation": c["validation"],
            "calculation_refs": [c["amortization"]["calculation_ref"]],
        }

    @staticmethod
    def _a10(c: dict[str, Any]) -> dict[str, Any]:
        action = c["deal"]["action"]
        return {
            "speaker": "BUSINESS_UPSIDE",
            "position": "SUPPORT" if action == "PROPOSE" else "ESCALATE" if action == "ESCALATE" else "OPPOSE",
            "claim": "preserve_viable_structure_with_explicit_controls",
            "residual_risks": c["assessment"]["unresolved_risks"],
        }

    @staticmethod
    def _a11(c: dict[str, Any]) -> dict[str, Any]:
        residual = list(c["assessment"]["unresolved_risks"])
        if c["financial"]["stressed_dscr"] < 1.0:
            residual.append("stress_case_below_1x")
        return {
            "speaker": "CONSERVATIVE_CREDIT",
            "position": "OPPOSE" if c["deal"]["action"] == "DECLINE" else "MODIFY" if residual else "SUPPORT",
            "challenges": "BUSINESS_UPSIDE",
            "residual_risks": sorted(set(residual)),
        }

    @staticmethod
    def _a12(c: dict[str, Any]) -> dict[str, Any]:
        policy_escalation = c["policy"]["escalation_required"]
        material_dissent = bool(c["risk_turns"][-1]["residual_risks"])
        return {
            "speaker": "NEUTRAL_GOVERNANCE",
            "position": "ESCALATE" if policy_escalation else "MODIFY" if material_dissent else "SUPPORT",
            "material_dissent": material_dissent,
            "escalation_required": policy_escalation,
            "auditability": "PASS",
            "residual_risks": c["risk_turns"][-1]["residual_risks"],
        }

    @staticmethod
    def _a13(c: dict[str, Any]) -> dict[str, Any]:
        reports = c["reports"]
        if c["data_quality"].get("critical_gap") or reports["cashflow"]["status"] == "PARTIAL":
            decision = "REJECT_INSUFFICIENT_EVIDENCE"
        elif not reports["financial_capacity"]["primary_repayment_viable"]:
            decision = "REJECT_INSUFFICIENT_EVIDENCE"
        elif reports["policy"]["escalation_required"] or reports["transaction_integrity"]["rating"] == "CRITICAL":
            decision = "ESCALATE_TO_CRO_RISK"
        elif c["deal"]["action"] == "PROPOSE":
            decision = "APPROVE_WITH_CONDITIONS"
        else:
            decision = "ESCALATE_TO_CRO_RISK"
        return {
            "status": "DRAFT",
            "decision": decision,
            "confidence": 0.9 if decision == "APPROVE_WITH_CONDITIONS" else 0.75,
            "decisive_findings": [
                reports["cashflow"]["rating"],
                reports["transaction_integrity"]["rating"],
                reports["financial_capacity"]["rating"],
                reports["policy"]["disposition"],
            ],
            "conditions": c["deal"].get("conditions", []),
            "residual_risks": c["risk_turns"][-1].get("residual_risks", []),
            "human_final_authority_required": True,
        }


class OpenAICompatibleModel(ModelAdapter):
    """Optional adapter for an OpenAI-compatible chat-completions endpoint."""

    name = "openai-compatible"

    def __init__(self) -> None:
        self.base_url = os.environ.get("CREDIT_AGENT_LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        self.api_key = os.environ.get("CREDIT_AGENT_LLM_API_KEY", "")
        self.model = os.environ.get("CREDIT_AGENT_LLM_MODEL", "")
        if not self.api_key or not self.model:
            raise ValueError("CREDIT_AGENT_LLM_API_KEY and CREDIT_AGENT_LLM_MODEL are required")

    def generate(self, node_id: str, system_prompt: str, context: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": "Return a JSON object for this role from this untrusted runtime context:\n"
                    + json.dumps(context, ensure_ascii=False, default=str),
                },
            ],
        }
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode(),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=90) as response:
            body = json.loads(response.read())
        return json.loads(body["choices"][0]["message"]["content"])
