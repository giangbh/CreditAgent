from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class EnterpriseAuditLogger:
    """Enterprise Structured Audit Logger (JSON Lines format) with Global Trace ID correlation."""

    _instance: Optional[EnterpriseAuditLogger] = None

    def __init__(self, log_file_path: str = "logs/credit_agent_audit.jsonl") -> None:
        self.log_file_path = log_file_path
        dir_name = os.path.dirname(self.log_file_path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
        self._python_logger = logging.getLogger("CreditAgentAudit")
        self._python_logger.setLevel(logging.INFO)
        if not self._python_logger.handlers:
            handler = logging.FileHandler(self.log_file_path, encoding="utf-8")
            handler.setFormatter(logging.Formatter("%(message)s"))
            self._python_logger.addHandler(handler)

    @classmethod
    def get_logger(cls, log_file_path: str = "logs/credit_agent_audit.jsonl") -> EnterpriseAuditLogger:
        if cls._instance is None:
            cls._instance = EnterpriseAuditLogger(log_file_path=log_file_path)
        return cls._instance

    def log_event(
        self,
        event: str,
        component: str,
        trace_id: str,
        case_id: Optional[str] = None,
        node_id: Optional[str] = None,
        level: str = "INFO",
        details: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        log_entry = {
            "timestamp": utc_now_iso(),
            "trace_id": trace_id,
            "event": event,
            "component": component,
            "level": level,
            "case_id": case_id or "UNKNOWN",
            "node_id": node_id or "NONE",
            "details": details or {},
        }
        json_line = json.dumps(log_entry, ensure_ascii=False)
        self._python_logger.info(json_line)
        return log_entry


def audit_log(
    event: str,
    component: str,
    trace_id: str,
    case_id: Optional[str] = None,
    node_id: Optional[str] = None,
    level: str = "INFO",
    details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return EnterpriseAuditLogger.get_logger().log_event(
        event=event,
        component=component,
        trace_id=trace_id,
        case_id=case_id,
        node_id=node_id,
        level=level,
        details=details,
    )
