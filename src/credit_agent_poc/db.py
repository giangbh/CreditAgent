from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Any, Generator, List, Optional, Union

from .models import AuditEvent, CreditState, utc_now


class StateRepository:
    """SQLite-backed persistent store for CreditState, checkpoints, and audit trails.
    Designed with a PostgreSQL-compatible schema structure for seamless future migration.
    """

    def __init__(self, db_path: Union[str, Path] = "credit_agent.db") -> None:
        self.db_path = str(db_path)
        self._persistent_conn: Optional[sqlite3.Connection] = None
        if self.db_path == ":memory:":
            self._persistent_conn = sqlite3.connect(":memory:", check_same_thread=False)
            self._persistent_conn.row_factory = sqlite3.Row
        self._init_db()

    @contextmanager
    def _connect(self) -> Generator[sqlite3.Connection, None, None]:
        if self._persistent_conn is not None:
            yield self._persistent_conn
            self._persistent_conn.commit()
        else:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS credit_cases (
                    case_id TEXT PRIMARY KEY,
                    scenario_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    state_version INTEGER NOT NULL DEFAULT 0,
                    case_revision INTEGER NOT NULL DEFAULT 1,
                    state_data TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS state_checkpoints (
                    checkpoint_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    after_node TEXT NOT NULL,
                    agent_name TEXT NOT NULL,
                    state_version INTEGER NOT NULL,
                    state_hash TEXT NOT NULL,
                    changed_paths TEXT NOT NULL,
                    state_snapshot TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    event TEXT NOT NULL,
                    node_id TEXT NOT NULL,
                    details TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS human_decisions (
                    decision_id TEXT PRIMARY KEY,
                    case_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    username TEXT NOT NULL,
                    full_name TEXT NOT NULL,
                    role TEXT NOT NULL,
                    branch_id TEXT NOT NULL,
                    ai_decision TEXT NOT NULL,
                    human_decision TEXT NOT NULL,
                    decision_type TEXT NOT NULL,
                    override_reason_category TEXT,
                    override_justification TEXT,
                    approved_amount INTEGER,
                    approved_tenor_months INTEGER,
                    approved_interest_rate REAL,
                    digital_signature_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

    def save_case(self, state: CreditState) -> None:
        snapshot = state.public_snapshot()
        state_data_json = json.dumps(snapshot, ensure_ascii=False)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO credit_cases (case_id, scenario_id, run_id, state_version, case_revision, state_data)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(case_id) DO UPDATE SET
                    scenario_id = excluded.scenario_id,
                    run_id = excluded.run_id,
                    state_version = excluded.state_version,
                    case_revision = excluded.case_revision,
                    state_data = excluded.state_data,
                    updated_at = CURRENT_TIMESTAMP;
                """,
                (
                    state.case_id,
                    state.scenario_id,
                    state.run_id,
                    state.state_version,
                    state.case_revision,
                    state_data_json,
                ),
            )

    def load_case(self, case_id: str) -> Optional[CreditState]:
        with self._connect() as conn:
            row = conn.execute("SELECT state_data FROM credit_cases WHERE case_id = ?", (case_id,)).fetchone()
            if not row:
                return None
            data = json.loads(row["state_data"])
            audit_events = [AuditEvent(**evt) for evt in data.get("audit", [])]
            data["audit"] = audit_events
            return CreditState(**data)

    def save_checkpoint(self, run_id: str, checkpoint: dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO state_checkpoints (
                    checkpoint_id, run_id, after_node, agent_name, state_version, state_hash, changed_paths, state_snapshot
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(checkpoint_id) DO UPDATE SET
                    state_version = excluded.state_version,
                    state_hash = excluded.state_hash,
                    changed_paths = excluded.changed_paths,
                    state_snapshot = excluded.state_snapshot;
                """,
                (
                    checkpoint["checkpoint_id"],
                    run_id,
                    checkpoint["after_node"],
                    checkpoint["agent_name"],
                    checkpoint["state_version"],
                    checkpoint["state_hash"],
                    json.dumps(checkpoint["changed_paths"], ensure_ascii=False),
                    json.dumps(checkpoint["state_snapshot"], ensure_ascii=False),
                ),
            )

    def get_checkpoints(self, run_id: str) -> List[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT checkpoint_id, after_node, agent_name, state_version, state_hash, changed_paths, state_snapshot
                FROM state_checkpoints WHERE run_id = ? ORDER BY state_version ASC;
                """,
                (run_id,),
            ).fetchall()
            result = []
            for row in rows:
                result.append(
                    {
                        "checkpoint_id": row["checkpoint_id"],
                        "after_node": row["after_node"],
                        "agent_name": row["agent_name"],
                        "state_version": row["state_version"],
                        "state_hash": row["state_hash"],
                        "changed_paths": json.loads(row["changed_paths"]),
                        "state_snapshot": json.loads(row["state_snapshot"]),
                    }
                )
            return result

    def log_audit_event(self, run_id: str, event: AuditEvent) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO audit_events (run_id, event, node_id, details, timestamp)
                VALUES (?, ?, ?, ?, ?);
                """,
                (
                    run_id,
                    event.event,
                    event.node_id,
                    json.dumps(event.details, ensure_ascii=False),
                    event.timestamp,
                ),
            )

    def record_human_decision(self, data: dict[str, Any]) -> dict[str, Any]:
        decision_id = data.get("decision_id") or f"DECISION-{uuid.uuid4().hex[:8]}"
        case_id = data["case_id"]
        run_id = data.get("run_id", "")
        user_id = data.get("user_id", "USR-8821")
        username = data.get("username", "nguyenvana")
        full_name = data.get("full_name", "Nguyễn Văn A")
        role = data.get("role", "CRO / Giám đốc Tín dụng")
        branch_id = data.get("branch_id", "HO_RISK_CENTER")
        ai_decision = data.get("ai_decision", "UNKNOWN")
        human_decision = data.get("human_decision", "APPROVED")
        decision_type = data.get("decision_type")
        if not decision_type:
            decision_type = "AGREE_WITH_AI" if human_decision == ai_decision else "OVERRIDE_AI"

        override_reason_category = data.get("override_reason_category")
        override_justification = data.get("override_justification")

        if decision_type == "OVERRIDE_AI" and (not override_justification or len(override_justification.strip()) < 10):
            raise ValueError("Lời giải trình (override_justification) là bắt buộc và phải có ít nhất 10 ký tự khi phủ quyết AI.")

        approved_amount = data.get("approved_amount")
        approved_tenor_months = data.get("approved_tenor_months")
        approved_interest_rate = data.get("approved_interest_rate")

        created_at = data.get("created_at") or utc_now()
        sig_payload = f"{decision_id}|{case_id}|{user_id}|{human_decision}|{decision_type}|{created_at}"
        digital_signature_hash = hashlib.sha256(sig_payload.encode()).hexdigest()

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO human_decisions (
                    decision_id, case_id, run_id, user_id, username, full_name, role, branch_id,
                    ai_decision, human_decision, decision_type, override_reason_category,
                    override_justification, approved_amount, approved_tenor_months, approved_interest_rate,
                    digital_signature_hash, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(decision_id) DO UPDATE SET
                    human_decision = excluded.human_decision,
                    decision_type = excluded.decision_type,
                    override_reason_category = excluded.override_reason_category,
                    override_justification = excluded.override_justification,
                    approved_amount = excluded.approved_amount,
                    approved_tenor_months = excluded.approved_tenor_months,
                    approved_interest_rate = excluded.approved_interest_rate,
                    digital_signature_hash = excluded.digital_signature_hash;
                """,
                (
                    decision_id,
                    case_id,
                    run_id,
                    user_id,
                    username,
                    full_name,
                    role,
                    branch_id,
                    ai_decision,
                    human_decision,
                    decision_type,
                    override_reason_category,
                    override_justification,
                    approved_amount,
                    approved_tenor_months,
                    approved_interest_rate,
                    digital_signature_hash,
                    created_at,
                ),
            )
        return {
            "decision_id": decision_id,
            "case_id": case_id,
            "user_id": user_id,
            "username": username,
            "full_name": full_name,
            "role": role,
            "decision_type": decision_type,
            "human_decision": human_decision,
            "digital_signature_hash": digital_signature_hash,
            "created_at": created_at,
            "status": "SUCCESS",
        }

    def get_human_decisions_by_case(self, case_id: str) -> List[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM human_decisions WHERE case_id = ? ORDER BY created_at DESC", (case_id,)
            ).fetchall()
            return [dict(row) for row in rows]

    def get_human_decisions_by_user(self, user_id: str) -> List[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM human_decisions WHERE user_id = ? ORDER BY created_at DESC", (user_id,)
            ).fetchall()
            return [dict(row) for row in rows]

    def generate_approver_quality_report(self, user_id: Optional[str] = None) -> dict[str, Any]:
        with self._connect() as conn:
            if user_id:
                rows = conn.execute("SELECT * FROM human_decisions WHERE user_id = ?", (user_id,)).fetchall()
            else:
                rows = conn.execute("SELECT * FROM human_decisions").fetchall()

            records = [dict(row) for row in rows]
            total_count = len(records)
            if total_count == 0:
                return {
                    "total_decisions": 0,
                    "agreed_with_ai_count": 0,
                    "override_ai_count": 0,
                    "agreement_rate_pct": 0.0,
                    "override_rate_pct": 0.0,
                    "quality_index": "NO_DATA",
                    "decisions": [],
                }

            override_count = sum(1 for r in records if r["decision_type"] == "OVERRIDE_AI")
            agree_count = total_count - override_count
            override_rate = round((override_count / total_count) * 100, 2)
            agree_rate = round((agree_count / total_count) * 100, 2)

            quality_index = "HIGH_COMPLIANCE"
            if override_rate > 35.0:
                quality_index = "HIGH_OVERRIDE_RISK"
            elif override_rate > 15.0:
                quality_index = "BALANCED_AUDITED"

            return {
                "user_id": user_id or "ALL_APPROVERS",
                "total_decisions": total_count,
                "agreed_with_ai_count": agree_count,
                "override_ai_count": override_count,
                "agreement_rate_pct": agree_rate,
                "override_rate_pct": override_rate,
                "quality_index": quality_index,
                "decisions": records,
            }
