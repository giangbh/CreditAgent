from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Any, Generator, List, Optional, Union

from .models import AuditEvent, CreditState


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
