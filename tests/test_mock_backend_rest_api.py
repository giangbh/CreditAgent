from __future__ import annotations

import json
import socket
import threading
import unittest
from http.server import ThreadingHTTPServer

from credit_agent_poc.models import CreditState, ToolExecutionError
from credit_agent_poc.scenarios import SCENARIOS
from credit_agent_poc.tools import ToolGateway
from credit_agent_poc.tools.adapters.rest_backend_adapter import RESTBackendAdapter
from credit_agent_poc.tools.simulated.mock_server import (
    MOCK_BACKEND_STATE,
    REST_TOOL_PATH_MAP,
    MockBackendServiceHandler,
)
from credit_agent_poc.web import POCRequestHandler


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class MockBackendRESTApiTests(unittest.TestCase):
    def setUp(self) -> None:
        MOCK_BACKEND_STATE.reset()

    def tearDown(self) -> None:
        MOCK_BACKEND_STATE.reset()

    def test_mock_backend_control_apis(self) -> None:
        # GET health
        status, res = MockBackendServiceHandler.handle_request("/api/v1/mock-backend/health", method="GET")
        self.assertEqual(status, 200)
        self.assertEqual(res["status"], "UP")
        self.assertEqual(res["active_scenario"], "approve_conditions")

        # GET scenarios catalog
        status, res = MockBackendServiceHandler.handle_request("/api/v1/mock-backend/scenarios", method="GET")
        self.assertEqual(status, 200)
        self.assertIn("available_scenarios", res)

        # POST scenario switch
        status, res = MockBackendServiceHandler.handle_request(
            "/api/v1/mock-backend/scenario",
            method="POST",
            body_dict={"scenario_id": "escalate_circular_funds"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(res["active_scenario_id"], "escalate_circular_funds")
        self.assertEqual(MOCK_BACKEND_STATE.active_scenario_id, "escalate_circular_funds")

        # POST reset
        status, res = MockBackendServiceHandler.handle_request("/api/v1/mock-backend/reset", method="POST")
        self.assertEqual(status, 200)
        self.assertEqual(MOCK_BACKEND_STATE.active_scenario_id, "approve_conditions")

    def test_all_25_tools_rest_endpoints(self) -> None:
        for service_path, tool_name in REST_TOOL_PATH_MAP.items():
            with self.subTest(tool_name=tool_name, service_path=service_path):
                status, res = MockBackendServiceHandler.handle_request(
                    service_path,
                    method="POST",
                    body_dict={"scenario_id": "approve_conditions"},
                )
                self.assertEqual(status, 200, f"Failed for {tool_name} at {service_path}: {res}")
                self.assertEqual(res["status"], "SUCCESS")
                self.assertEqual(res["tool_name"], tool_name)
                self.assertIsInstance(res["data"], dict)
                self.assertIn("system", res["data"])

    def test_scenario_specific_backend_responses(self) -> None:
        # 1. Circular Funds Scenario
        status, res = MockBackendServiceHandler.handle_request(
            "/api/v1/graph-fraud/detect-cycles",
            method="POST",
            body_dict={"scenario_id": "escalate_circular_funds"},
        )
        self.assertEqual(status, 200)
        self.assertGreaterEqual(res["data"]["cycle_score"], 0.7)
        self.assertTrue(len(res["data"]["detected_cycles"]) > 0)

        # 2. Missing Evidence Scenario
        status, res = MockBackendServiceHandler.handle_request(
            "/api/v1/dms/validate-completeness",
            method="POST",
            body_dict={"scenario_id": "reject_missing_evidence"},
        )
        self.assertEqual(status, 200)
        self.assertFalse(res["data"]["complete"])
        self.assertIn("financial_statement", res["data"]["missing"])

        # 3. Policy Exception Scenario
        status, res = MockBackendServiceHandler.handle_request(
            "/api/v1/policy-bre/evaluate-rule",
            method="POST",
            body_dict={"scenario_id": "escalate_policy_exception"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(res["data"]["disposition"], "MANDATORY_ESCALATION")
        self.assertEqual(res["data"]["rule_id"], "RULE-TENOR-003")

        # 4. Weak Cashflow Scenario
        status, res = MockBackendServiceHandler.handle_request(
            "/api/v1/cashflow/credit-capacity",
            method="POST",
            body_dict={"scenario_id": "reject_weak_cashflow_high_collateral"},
        )
        self.assertEqual(status, 200)
        self.assertFalse(res["data"]["primary_repayment_viable"])

    def test_error_simulation(self) -> None:
        # Simulate HTTP 503 error on compute_cashflow_metrics
        status, res = MockBackendServiceHandler.handle_request(
            "/api/v1/mock-backend/simulate-error",
            method="POST",
            body_dict={"target": "compute_cashflow_metrics", "status_code": 503},
        )
        self.assertEqual(status, 200)

        # Invoking compute_cashflow_metrics should return 503
        status, res = MockBackendServiceHandler.handle_request("/api/v1/cashflow/metrics", method="POST")
        self.assertEqual(status, 503)
        self.assertEqual(res["error"], "SIMULATED_BACKEND_SERVICE_ERROR")

        # REST adapter should raise ToolExecutionError
        adapter = RESTBackendAdapter(use_in_process_http=True)
        with self.assertRaises(ToolExecutionError):
            adapter.execute("compute_cashflow_metrics", SCENARIOS["approve_conditions"], {})

    def test_rest_backend_adapter_in_process(self) -> None:
        adapter = RESTBackendAdapter(use_in_process_http=True)
        self.assertTrue(adapter.is_healthy())

        data = adapter.execute("document_inventory", SCENARIOS["approve_conditions"], {})
        self.assertIsInstance(data, dict)
        self.assertEqual(data["system"], "DMS_ECM")

    def test_live_http_server_mock_backend(self) -> None:
        port = find_free_port()
        server = ThreadingHTTPServer(("127.0.0.1", port), POCRequestHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        try:
            adapter = RESTBackendAdapter(endpoint_url=f"http://127.0.0.1:{port}")
            self.assertTrue(adapter.is_healthy())

            # Test multiple tool calls over real HTTP network socket
            for tool_name in [
                "document_inventory",
                "resolve_borrower_identity",
                "compute_cashflow_metrics",
                "detect_transaction_cycles",
                "evaluate_policy_rule",
                "validate_deal_structure",
            ]:
                data = adapter.execute(tool_name, SCENARIOS["approve_conditions"], {})
                self.assertIsInstance(data, dict)
                self.assertIn("system", data)
        finally:
            server.shutdown()
            server.server_close()

    def test_tool_gateway_integration_with_rest_adapter(self) -> None:
        adapter = RESTBackendAdapter(use_in_process_http=True)
        gateway = ToolGateway(backend=adapter)

        state = CreditState(case_id="CASE-REST-001", scenario_id="approve_conditions", run_id="run-rest-001", trace_id="tr-rest-001")
        response = gateway.call(
            node_id="A2",
            state=state,
            scenario=SCENARIOS["approve_conditions"],
            tool_name="query_transactions",
            arguments={"limit": 10},
        )

        self.assertEqual(response["status"], "SUCCESS")
        self.assertEqual(response["tool_name"], "query_transactions")
        self.assertIn("data", response)
        self.assertEqual(response["data"]["system"], "CORE_BANKING_TRANSACTIONS")
