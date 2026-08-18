from __future__ import annotations

import json
from typing import Any, Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from ....models import ToolExecutionError
from ....scenarios import Scenario
from ..base_adapter import BaseBankAdapter
from ...simulated.mock_server import TOOL_TO_REST_PATH_MAP, MockBackendServiceHandler


class RESTBackendAdapter(BaseBankAdapter):
    """HTTP REST Adapter connecting CreditAgent ToolGateway to mock backend REST API services."""

    system_code: str = "REST_BANK_BACKEND"
    description: str = "Enterprise Banking REST API Adapter (Mock)"

    def __init__(self, endpoint_url: Optional[str] = None, api_key: Optional[str] = None, use_in_process_http: bool = False) -> None:
        super().__init__(endpoint_url=endpoint_url, api_key=api_key)
        self.use_in_process_http = use_in_process_http or (endpoint_url is None)

    def is_healthy(self) -> bool:
        if self.use_in_process_http:
            status, res = MockBackendServiceHandler.handle_request("/api/v1/mock-backend/health", method="GET")
            return status == 200
        try:
            url = f"{self.endpoint_url}/api/v1/mock-backend/health"
            req = Request(url, headers={"Accept": "application/json"})
            with urlopen(req, timeout=2.0) as resp:
                return resp.status == 200
        except Exception:
            return False

    def execute(self, tool_name: str, scenario: Scenario, arguments: dict[str, Any]) -> dict[str, Any]:
        """Execute backend tool invocation via HTTP REST API endpoint."""
        if tool_name not in TOOL_TO_REST_PATH_MAP:
            raise ToolExecutionError(f"Unknown REST service mapping for tool: {tool_name}")

        service_path = TOOL_TO_REST_PATH_MAP[tool_name]
        payload = {
            "scenario_id": scenario.scenario_id,
            "arguments": arguments,
        }

        # 1. In-process dispatch mode (for fast unit testing without bound port)
        if self.use_in_process_http:
            status, res = MockBackendServiceHandler.handle_request(service_path, method="POST", body_dict=payload)
            if status == 200:
                return res.get("data", {})
            error_msg = res.get("message") or res.get("error") or f"HTTP {status}"
            raise ToolExecutionError(f"REST service error ({tool_name}): {error_msg}")

        # 2. Real HTTP REST Network Call mode
        url = f"{self.endpoint_url}{service_path}"
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = Request(url, data=body, headers=headers, method="POST")

        try:
            with urlopen(req, timeout=5.0) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))
                return resp_data.get("data", {})
        except HTTPError as exc:
            try:
                err_body = json.loads(exc.read().decode("utf-8"))
                msg = err_body.get("message") or err_body.get("error") or str(exc)
            except Exception:
                msg = str(exc)
            raise ToolExecutionError(f"REST API error ({tool_name}) HTTP {exc.code}: {msg}")
        except URLError as exc:
            raise ToolExecutionError(f"REST API connection failure ({tool_name}): {exc.reason}")
        except Exception as exc:
            raise ToolExecutionError(f"REST API call failed ({tool_name}): {str(exc)}")

    def query(self, action: str, params: dict[str, Any]) -> dict[str, Any]:
        """Generic adapter query interface implementation."""
        scenario = params.get("scenario")
        if not scenario:
            from ....scenarios import SCENARIOS
            scenario = SCENARIOS["approve_conditions"]
        return self.execute(tool_name=action, scenario=scenario, arguments=params.get("arguments", {}))
