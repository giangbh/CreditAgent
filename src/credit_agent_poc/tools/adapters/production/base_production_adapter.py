from __future__ import annotations

import json
from typing import Any, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ....models import ToolExecutionError
from ..base_adapter import BaseBankAdapter


class BaseProductionHTTPAdapter(BaseBankAdapter):
    """Base class for Production Bank Adapters making HTTP/HTTPS REST calls to enterprise services."""

    def __init__(
        self,
        endpoint_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout_sec: float = 10.0,
    ) -> None:
        super().__init__(endpoint_url=endpoint_url, api_key=api_key)
        self.timeout_sec = timeout_sec

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.endpoint_url}{path}"
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "CreditAgent-EnterpriseGateway/2.0",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = Request(url, data=body, headers=headers, method="POST")

        try:
            with urlopen(req, timeout=self.timeout_sec) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data
        except HTTPError as exc:
            try:
                err_body = json.loads(exc.read().decode("utf-8"))
                msg = err_body.get("message") or err_body.get("error") or str(exc)
            except Exception:
                msg = str(exc)
            raise ToolExecutionError(f"{self.system_code} API HTTP {exc.code}: {msg}")
        except URLError as exc:
            raise ToolExecutionError(f"{self.system_code} API connection failure: {exc.reason}")
        except Exception as exc:
            raise ToolExecutionError(f"{self.system_code} API call failed: {str(exc)}")
