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
                CREATE TABLE IF NOT EXISTS decision_acknowledgements (
                    acknowledgement_id TEXT PRIMARY KEY,
                    case_id TEXT NOT NULL,
                    opinion_id TEXT NOT NULL,
                    opinion_version INTEGER NOT NULL,
                    actor_id TEXT NOT NULL,
                    warning_hash TEXT NOT NULL,
                    acknowledged_finding_ids TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'ACTIVE',
                    superseded_reason TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS human_decisions (
                    decision_id TEXT PRIMARY KEY,
                    case_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    opinion_id TEXT,
                    opinion_version INTEGER,
                    acknowledged_finding_ids TEXT,
                    warning_hash TEXT,
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
                    integrity_seal_hash TEXT NOT NULL,
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
        opinion_id = data.get("opinion_id", "")
        opinion_version = data.get("opinion_version", 1)
        acknowledged_finding_ids = json.dumps(data.get("acknowledged_finding_ids", []), ensure_ascii=False)
        warning_hash = data.get("warning_hash", "")
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
        sig_payload = f"{decision_id}|{case_id}|{opinion_id}|{opinion_version}|{user_id}|{human_decision}|{decision_type}|{created_at}"
        integrity_seal_hash = hashlib.sha256(sig_payload.encode("utf-8")).hexdigest()

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO human_decisions (
                    decision_id, case_id, run_id, opinion_id, opinion_version, acknowledged_finding_ids, warning_hash,
                    user_id, username, full_name, role, branch_id,
                    ai_decision, human_decision, decision_type, override_reason_category,
                    override_justification, approved_amount, approved_tenor_months, approved_interest_rate,
                    integrity_seal_hash, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(decision_id) DO UPDATE SET
                    opinion_id = excluded.opinion_id,
                    opinion_version = excluded.opinion_version,
                    acknowledged_finding_ids = excluded.acknowledged_finding_ids,
                    warning_hash = excluded.warning_hash,
                    human_decision = excluded.human_decision,
                    decision_type = excluded.decision_type,
                    override_reason_category = excluded.override_reason_category,
                    override_justification = excluded.override_justification,
                    approved_amount = excluded.approved_amount,
                    approved_tenor_months = excluded.approved_tenor_months,
                    approved_interest_rate = excluded.approved_interest_rate,
                    integrity_seal_hash = excluded.integrity_seal_hash;
                """,
                (
                    decision_id,
                    case_id,
                    run_id,
                    opinion_id,
                    opinion_version,
                    acknowledged_finding_ids,
                    warning_hash,
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
                    integrity_seal_hash,
                    created_at,
                ),
            )
        return {
            "decision_id": decision_id,
            "case_id": case_id,
            "user_id": user_id,
            "human_decision": human_decision,
            "decision_type": decision_type,
            "integrity_seal_hash": integrity_seal_hash,
            "digital_signature_hash": integrity_seal_hash,  # alias for backward compatibility
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

            qa_sampling_tier = "STANDARD_QA_SAMPLING"
            if override_rate > 35.0:
                qa_sampling_tier = "PRIORITY_QA_SAMPLING"
            elif override_rate > 15.0:
                qa_sampling_tier = "ROUTINE_QA_SAMPLING"

            return {
                "user_id": user_id or "ALL",
                "total_decisions": total_count,
                "agreed_with_ai_count": agree_count,
                "override_ai_count": override_count,
                "agreement_rate_pct": agree_rate,
                "override_rate_pct": override_rate,
                "qa_sampling_tier": qa_sampling_tier,
                "quality_index": qa_sampling_tier,  # alias for backward compatibility
                "decisions": records,
            }

    def evaluate_control_gate(
        self,
        case_id: str,
        opinion: Optional[Dict[str, Any]],
        current_case_revision: int = 1,
        actor_role: str = "BRANCH_DIRECTOR",
    ) -> Tuple[List[str], List[str]]:
        allowed_actions: List[str] = ["VIEW", "REQUEST_INFO", "REANALYZE", "ESCALATE", "REJECT", "WITHDRAW"]
        blocked_reasons: List[str] = []

        if not opinion or opinion.get("status") != "VALIDATED":
            blocked_reasons.append("NO_VALID_OPINION")
            return allowed_actions, blocked_reasons

        opinion_revision = opinion.get("case_revision", 1)
        if opinion_revision != current_case_revision:
            blocked_reasons.append("OPINION_STALE")
            return allowed_actions, blocked_reasons

        is_hard_block = opinion.get("hard_block", False)
        decision = opinion.get("decision", "")

        if is_hard_block and actor_role not in ("CRO", "CREDIT_AUTHORITY"):
            blocked_reasons.append("HARD_BLOCK_REQUIRES_AUTHORITY")

        if decision == "APPROVE_WITH_CONDITIONS" and not is_hard_block:
            allowed_actions.append("SIGN")
            allowed_actions.append("SIGN_WITH_DIVERGENCE")
        else:
            allowed_actions.append("SIGN_WITH_DIVERGENCE")

        return allowed_actions, blocked_reasons

    def record_acknowledgement(
        self,
        case_id: str,
        opinion_id: str,
        opinion_version: int,
        actor_id: str,
        warning_hash: str,
        acknowledged_finding_ids: List[str],
    ) -> str:
        ack_id = f"ACK-{uuid.uuid4().hex[:8]}"
        findings_json = json.dumps(acknowledged_finding_ids, ensure_ascii=False)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO decision_acknowledgements (
                    acknowledgement_id, case_id, opinion_id, opinion_version, actor_id, warning_hash, acknowledged_finding_ids, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'ACTIVE')
                """,
                (ack_id, case_id, opinion_id, opinion_version, actor_id, warning_hash, findings_json),
            )
        return ack_id

    def get_active_acknowledgement(self, case_id: str, opinion_version: int) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM decision_acknowledgements WHERE case_id = ? AND opinion_version = ? AND status = 'ACTIVE'",
                (case_id, opinion_version),
            ).fetchone()
            return dict(row) if row else None

    def supersede_acknowledgements_for_case(self, case_id: str, reason: str = "NEW_CASE_REVISION") -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE decision_acknowledgements SET status = 'SUPERSEDED', superseded_reason = ? WHERE case_id = ? AND status = 'ACTIVE'",
                (reason, case_id),
            )

    def record_human_decision_v2(self, payload: Dict[str, Any], opinion_dict: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        case_id = payload["case_id"]
        action = payload.get("action", "SIGN")
        actor_role = payload.get("actor_role", "BRANCH_DIRECTOR")
        actor_id = payload.get("actor_id", "USR-101")
        idempotency_key = payload.get("idempotency_key", "")

        if idempotency_key:
            with self._connect() as conn:
                existing = conn.execute(
                    "SELECT * FROM human_decisions WHERE case_id = ? AND user_id = ? AND decision_id LIKE ?",
                    (case_id, actor_id, f"%{idempotency_key}%"),
                ).fetchone()
                if existing:
                    rec = dict(existing)
                    return {
                        "decision_id": rec["decision_id"],
                        "case_id": rec["case_id"],
                        "user_id": rec["user_id"],
                        "human_decision": rec["human_decision"],
                        "decision_type": rec["decision_type"],
                        "integrity_seal": rec["integrity_seal_hash"],
                        "status": "SUCCESS_IDEMPOTENT",
                    }

        allowed_actions, blocked_reasons = self.evaluate_control_gate(case_id, opinion_dict, actor_role=actor_role)

        if opinion_dict and opinion_dict.get("hard_block") and actor_role not in ("CRO", "CREDIT_AUTHORITY"):
            raise ValueError("403: INSUFFICIENT_AUTHORITY - Action blocked by hard_block policy.")

        if action not in allowed_actions:
            raise ValueError(f"409: ACTION_NOT_ALLOWED - Action '{action}' is not in allowed_actions: {allowed_actions}")

        alignment = payload.get("alignment", "CONCURRENT")
        reason_code = payload.get("divergence_reason_code")
        narrative = payload.get("divergence_narrative", "")

        if alignment == "DIVERGENT":
            if not reason_code:
                raise ValueError("422: REASON_CODE_REQUIRED - Divergent decision requires a reason code.")
            if not narrative or len(narrative.strip()) < 120:
                raise ValueError("422: NARRATIVE_TOO_SHORT - Divergence narrative must be at least 120 characters.")

        decision_id = f"DECISION-{idempotency_key}" if idempotency_key else f"DECISION-{uuid.uuid4().hex[:8]}"
        opinion_id = payload.get("opinion_id") or (opinion_dict.get("opinion_id") if opinion_dict else "")
        opinion_version = payload.get("opinion_version") or (opinion_dict.get("opinion_version") if opinion_dict else 1)
        human_decision = payload.get("human_decision", "APPROVED")
        created_at = payload.get("created_at") or utc_now()

        sig_payload = f"{decision_id}|{case_id}|{opinion_id}|{opinion_version}|{actor_id}|{human_decision}|{alignment}|{payload.get('approved_amount')}|{created_at}"
        integrity_seal = hashlib.sha256(sig_payload.encode("utf-8")).hexdigest()

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO human_decisions (
                    decision_id, case_id, run_id, opinion_id, opinion_version, acknowledged_finding_ids, warning_hash,
                    user_id, username, full_name, role, branch_id, ai_decision, human_decision, decision_type,
                    override_reason_category, override_justification, approved_amount, approved_tenor_months,
                    approved_interest_rate, integrity_seal_hash, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    decision_id,
                    case_id,
                    payload.get("run_id", ""),
                    opinion_id,
                    opinion_version,
                    json.dumps(payload.get("acknowledged_finding_ids", []), ensure_ascii=False),
                    payload.get("warning_hash", ""),
                    actor_id,
                    payload.get("username", "nguyenvana"),
                    payload.get("full_name", "Nguyễn Văn A"),
                    actor_role,
                    payload.get("branch_id", "HO_RISK"),
                    opinion_dict.get("decision", "UNKNOWN") if opinion_dict else "UNKNOWN",
                    human_decision,
                    alignment,
                    reason_code,
                    narrative,
                    payload.get("approved_amount"),
                    payload.get("approved_tenor_months"),
                    payload.get("approved_interest_rate"),
                    integrity_seal,
                    created_at,
                ),
            )

        return {
            "decision_id": decision_id,
            "case_id": case_id,
            "user_id": actor_id,
            "human_decision": human_decision,
            "decision_type": alignment,
            "integrity_seal": integrity_seal,
            "status": "SUCCESS",
        }

    def verify_decision_integrity_seal(self, decision_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM human_decisions WHERE decision_id = ?", (decision_id,)).fetchone()
            if not row:
                return False
            rec = dict(row)
            sig_payload = f"{rec['decision_id']}|{rec['case_id']}|{rec['opinion_id'] or ''}|{rec['opinion_version'] or 1}|{rec['user_id']}|{rec['human_decision']}|{rec['decision_type']}|{rec['approved_amount']}|{rec['created_at']}"
            computed_seal = hashlib.sha256(sig_payload.encode("utf-8")).hexdigest()
            return computed_seal == rec["integrity_seal_hash"]
