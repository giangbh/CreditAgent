from __future__ import annotations

from typing import Any, Optional
import json
import threading

from ...models import ToolExecutionError
from ...scenarios import SCENARIOS, Scenario, scenario_catalog
from .simulated_backend import SimulatedBackend

REST_TOOL_PATH_MAP: dict[str, str] = {
    "/api/v1/dms/inventory": "document_inventory",
    "/api/v1/dms/classify": "classify_document",
    "/api/v1/dms/extract-fields": "extract_document_fields",
    "/api/v1/dms/parse-statement": "parse_bank_statement",
    "/api/v1/dms/validate-completeness": "validate_case_completeness",

    "/api/v1/core-banking/identity": "resolve_borrower_identity",
    "/api/v1/core-banking/transactions": "query_transactions",

    "/api/v1/cashflow/metrics": "compute_cashflow_metrics",
    "/api/v1/cashflow/anomalies": "detect_cashflow_anomalies",
    "/api/v1/cashflow/reconcile-revenue": "reconcile_declared_revenue",
    "/api/v1/cashflow/credit-capacity": "calculate_credit_capacity",
    "/api/v1/cashflow/stress-test": "stress_repayment_capacity",
    "/api/v1/cashflow/refinancing-pattern": "assess_refinancing_pattern",

    "/api/v1/graph-fraud/entity-graph": "build_entity_transaction_graph",
    "/api/v1/graph-fraud/detect-cycles": "detect_transaction_cycles",
    "/api/v1/graph-fraud/trace-funds": "trace_funds",

    "/api/v1/policy-bre/search-policy": "search_policy",
    "/api/v1/policy-bre/get-clause": "get_policy_clause",
    "/api/v1/policy-bre/evaluate-rule": "evaluate_policy_rule",
    "/api/v1/policy-bre/validate-citation": "validate_policy_citation",
    "/api/v1/policy-bre/approval-authority": "resolve_approval_authority",

    "/api/v1/los-structuring/amortization": "calculate_amortization",
    "/api/v1/los-structuring/pricing-band": "resolve_pricing_band",
    "/api/v1/los-structuring/validate-deal": "validate_deal_structure",
    "/api/v1/los-structuring/retrieve-memory": "retrieve_approved_memory",
}

TOOL_TO_REST_PATH_MAP: dict[str, str] = {tool: path for path, tool in REST_TOOL_PATH_MAP.items()}


class MockBackendState:
    """Thread-safe global state manager for Mock Backend scenarios and forced error simulations."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.active_scenario_id: str = "approve_conditions"
        self.forced_errors: dict[str, int] = {}  # tool_name or path -> HTTP status code (e.g. 503, 500, 429)
        self.scenario_overrides: dict[str, Any] = {}
        self.backend = SimulatedBackend()

    def set_scenario(self, scenario_id: str, overrides: Optional[dict[str, Any]] = None) -> Scenario:
        with self._lock:
            if scenario_id not in SCENARIOS:
                raise ValueError(f"Unknown scenario_id: {scenario_id}")
            self.active_scenario_id = scenario_id
            self.scenario_overrides = overrides or {}
            base = SCENARIOS[scenario_id]
            if not self.scenario_overrides:
                return base
            # Apply dynamic field overrides
            return Scenario(
                scenario_id=base.scenario_id,
                name=base.name,
                description=base.description,
                expected_outcome=base.expected_outcome,
                borrower=self.scenario_overrides.get("borrower", base.borrower),
                request=self.scenario_overrides.get("request", base.request),
                documents_complete=self.scenario_overrides.get("documents_complete", base.documents_complete),
                statement_months=self.scenario_overrides.get("statement_months", base.statement_months),
                declared_revenue=self.scenario_overrides.get("declared_revenue", base.declared_revenue),
                observed_inflow=self.scenario_overrides.get("observed_inflow", base.observed_inflow),
                existing_debt_service=self.scenario_overrides.get("existing_debt_service", base.existing_debt_service),
                projected_debt_service=self.scenario_overrides.get("projected_debt_service", base.projected_debt_service),
                dscr=self.scenario_overrides.get("dscr", base.dscr),
                inflow_concentration=self.scenario_overrides.get("inflow_concentration", base.inflow_concentration),
                circular_funds_score=self.scenario_overrides.get("circular_funds_score", base.circular_funds_score),
                related_party_coverage=self.scenario_overrides.get("related_party_coverage", base.related_party_coverage),
                collateral_coverage=self.scenario_overrides.get("collateral_coverage", base.collateral_coverage),
                policy_exception=self.scenario_overrides.get("policy_exception", base.policy_exception),
                authority_escalation=self.scenario_overrides.get("authority_escalation", base.authority_escalation),
                forced_tool_failures=tuple(self.scenario_overrides.get("forced_tool_failures", base.forced_tool_failures)),
            )

    def get_current_scenario(self) -> Scenario:
        with self._lock:
            base = SCENARIOS.get(self.active_scenario_id, SCENARIOS["approve_conditions"])
            if not self.scenario_overrides:
                return base
            return Scenario(
                scenario_id=base.scenario_id,
                name=base.name,
                description=base.description,
                expected_outcome=base.expected_outcome,
                borrower=self.scenario_overrides.get("borrower", base.borrower),
                request=self.scenario_overrides.get("request", base.request),
                documents_complete=self.scenario_overrides.get("documents_complete", base.documents_complete),
                statement_months=self.scenario_overrides.get("statement_months", base.statement_months),
                declared_revenue=self.scenario_overrides.get("declared_revenue", base.declared_revenue),
                observed_inflow=self.scenario_overrides.get("observed_inflow", base.observed_inflow),
                existing_debt_service=self.scenario_overrides.get("existing_debt_service", base.existing_debt_service),
                projected_debt_service=self.scenario_overrides.get("projected_debt_service", base.projected_debt_service),
                dscr=self.scenario_overrides.get("dscr", base.dscr),
                inflow_concentration=self.scenario_overrides.get("inflow_concentration", base.inflow_concentration),
                circular_funds_score=self.scenario_overrides.get("circular_funds_score", base.circular_funds_score),
                related_party_coverage=self.scenario_overrides.get("related_party_coverage", base.related_party_coverage),
                collateral_coverage=self.scenario_overrides.get("collateral_coverage", base.collateral_coverage),
                policy_exception=self.scenario_overrides.get("policy_exception", base.policy_exception),
                authority_escalation=self.scenario_overrides.get("authority_escalation", base.authority_escalation),
                forced_tool_failures=tuple(self.scenario_overrides.get("forced_tool_failures", base.forced_tool_failures)),
            )

    def set_forced_error(self, tool_or_path: str, status_code: int = 503) -> None:
        with self._lock:
            self.forced_errors[tool_or_path] = status_code

    def reset(self) -> None:
        with self._lock:
            self.active_scenario_id = "approve_conditions"
            self.forced_errors.clear()
            self.scenario_overrides.clear()


# Global Mock Backend State Instance
MOCK_BACKEND_STATE = MockBackendState()


class MockBackendServiceHandler:
    """REST Dispatcher that handles incoming HTTP REST API requests for mock backend services."""

    @staticmethod
    def handle_request(path: str, method: str = "POST", body_dict: Optional[dict[str, Any]] = None) -> tuple[int, dict[str, Any]]:
        body_dict = body_dict or {}

        # 1. Handle Mock Control APIs
        if path == "/api/v1/mock-backend/health" and method == "GET":
            return 200, {
                "status": "UP",
                "active_scenario": MOCK_BACKEND_STATE.active_scenario_id,
                "forced_errors": MOCK_BACKEND_STATE.forced_errors,
            }

        if path == "/api/v1/mock-backend/scenarios" and method == "GET":
            return 200, {
                "active_scenario": MOCK_BACKEND_STATE.active_scenario_id,
                "available_scenarios": scenario_catalog(),
            }

        if path == "/api/v1/mock-backend/scenario" and method == "POST":
            scenario_id = body_dict.get("scenario_id")
            if not scenario_id or scenario_id not in SCENARIOS:
                return 400, {"error": "INVALID_SCENARIO_ID", "message": f"Scenario {scenario_id} not found."}
            overrides = body_dict.get("overrides")
            s = MOCK_BACKEND_STATE.set_scenario(scenario_id, overrides)
            return 200, {
                "status": "SCENARIO_UPDATED",
                "active_scenario_id": s.scenario_id,
                "overrides": overrides,
            }

        if path == "/api/v1/mock-backend/simulate-error" and method == "POST":
            target = body_dict.get("target")  # tool_name or REST path
            status_code = int(body_dict.get("status_code", 503))
            if not target:
                return 400, {"error": "MISSING_TARGET", "message": "Target tool_name or REST path is required."}
            MOCK_BACKEND_STATE.set_forced_error(target, status_code)
            return 200, {
                "status": "ERROR_SIMULATION_ACTIVE",
                "target": target,
                "simulated_status_code": status_code,
            }

        if path == "/api/v1/mock-backend/reset" and method == "POST":
            MOCK_BACKEND_STATE.reset()
            return 200, {"status": "RESET_SUCCESSFUL"}

        # 2. Dispatch Banking Tool REST Service Endpoints
        if path in REST_TOOL_PATH_MAP:
            tool_name = REST_TOOL_PATH_MAP[path]
            # Check for simulated HTTP error overrides
            if tool_name in MOCK_BACKEND_STATE.forced_errors:
                status = MOCK_BACKEND_STATE.forced_errors[tool_name]
                return status, {
                    "error": "SIMULATED_BACKEND_SERVICE_ERROR",
                    "tool_name": tool_name,
                    "status_code": status,
                    "message": f"Mock backend service for {tool_name} returned simulated HTTP {status}",
                }
            if path in MOCK_BACKEND_STATE.forced_errors:
                status = MOCK_BACKEND_STATE.forced_errors[path]
                return status, {
                    "error": "SIMULATED_BACKEND_SERVICE_ERROR",
                    "path": path,
                    "status_code": status,
                    "message": f"Mock backend endpoint {path} returned simulated HTTP {status}",
                }

            # Get active scenario context (either from body or global state)
            req_scenario_id = body_dict.get("scenario_id")
            if req_scenario_id and req_scenario_id in SCENARIOS:
                scenario = MOCK_BACKEND_STATE.set_scenario(req_scenario_id, body_dict.get("scenario_overrides"))
            else:
                scenario = MOCK_BACKEND_STATE.get_current_scenario()

            arguments = body_dict.get("arguments", body_dict)

            try:
                data = MOCK_BACKEND_STATE.backend.execute(tool_name, scenario, arguments)
                return 200, {
                    "status": "SUCCESS",
                    "service_path": path,
                    "tool_name": tool_name,
                    "scenario_id": scenario.scenario_id,
                    "data": data,
                }
            except ToolExecutionError as exc:
                return 503, {
                    "error": "TOOL_EXECUTION_FAILURE",
                    "tool_name": tool_name,
                    "scenario_id": scenario.scenario_id,
                    "message": str(exc),
                }

        return 404, {"error": "ENDPOINT_NOT_FOUND", "path": path}
