from __future__ import annotations

import json
import threading
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from urllib.parse import parse_qs, urlparse

from .db import StateRepository
from .orchestrator import CreditOrchestrator
from .scenarios import SCENARIOS, scenario_catalog


def is_temporal_cluster_alive(host: str = "127.0.0.1", port: int = 7233) -> bool:
    import socket
    try:
        with socket.create_connection((host, port), timeout=0.2):
            return True
    except Exception:
        return False


class POCRequestHandler(BaseHTTPRequestHandler):
    db_path: str = "credit_agent.db"
    orchestrator: Optional[CreditOrchestrator] = None
    runs: dict[str, dict] = {}
    runs_lock = threading.Lock()

    @classmethod
    def get_orchestrator(cls, step_delay_ms: int = 0, engine: Optional[str] = None) -> CreditOrchestrator:
        repo = StateRepository(db_path=cls.db_path)
        if not engine:
            engine = "temporal-cluster" if is_temporal_cluster_alive() else "temporal"
        return CreditOrchestrator(db_repository=repo, engine=engine, step_delay_ms=step_delay_ms)

    def log_message(self, format: str, *args: object) -> None:
        return

    def _json(self, payload: object, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        parsed_url = urlparse(self.path)
        path = parsed_url.path
        query = parse_qs(parsed_url.query)

        if path == "/api/scenarios":
            self._json(scenario_catalog())
            return
        if path == "/api/engine-info":
            cluster_alive = is_temporal_cluster_alive()
            active_engine = "temporal-cluster" if cluster_alive else "temporal"
            self._json({
                "cluster_alive": cluster_alive,
                "active_engine": active_engine,
                "engine_label": "Native Temporal Server Cluster (127.0.0.1:7233)" if cluster_alive else "Temporal.io Workflow Engine (In-Memory Simulation)",
                "temporal_ui_url": "http://localhost:8233" if cluster_alive else None,
            })
            return
        if path == "/api/health":
            cluster_alive = is_temporal_cluster_alive()
            self._json({
                "status": "ok",
                "service": "credit-agent-poc",
                "db": self.db_path,
                "temporal_cluster_alive": cluster_alive,
                "active_engine": "temporal-cluster" if cluster_alive else "temporal",
            })
            return
        status_prefix = "/api/run-status/"
        if path.startswith(status_prefix):
            run_id = path[len(status_prefix) :]
            with self.runs_lock:
                run = self.runs.get(run_id)
                payload = dict(run) if run else None
            if payload is None:
                self._json({"error": "unknown_run", "run_id": run_id}, HTTPStatus.NOT_FOUND)
            else:
                self._json(payload)
            return
        if path == "/api/approver-quality-report":
            query = parse_qs(urlparse(self.path).query)
            user_id = query.get("user_id", [None])[0]
            db = StateRepository(self.db_path)
            report = db.generate_approver_quality_report(user_id)
            self._json(report)
            return

        case_decisions_prefix = "/api/human-decisions/case/"
        if path.startswith(case_decisions_prefix):
            case_id = path[len(case_decisions_prefix) :]
            db = StateRepository(self.db_path)
            decisions = db.get_human_decisions_by_case(case_id)
            self._json({"case_id": case_id, "decisions": decisions})
            return

        user_decisions_prefix = "/api/human-decisions/user/"
        if path.startswith(user_decisions_prefix):
            user_id = path[len(user_decisions_prefix) :]
            db = StateRepository(self.db_path)
            decisions = db.get_human_decisions_by_user(user_id)
            self._json({"user_id": user_id, "decisions": decisions})
            return

        if path in {"/", "/index.html"}:
            body = files("credit_agent_poc").joinpath("static/index.html").read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self._json({"error": "not_found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/human-decision":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length) if content_length > 0 else b"{}"
            try:
                data = json.loads(body)
                db = StateRepository(self.db_path)
                result = db.record_human_decision(data)
                self._json(result, HTTPStatus.CREATED)
            except ValueError as exc:
                self._json({"error": "invalid_request", "message": str(exc)}, HTTPStatus.BAD_REQUEST)
            except Exception as exc:
                self._json({"error": "record_failed", "message": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        async_prefix = "/api/run-async/"
        parsed_url = urlparse(self.path)
        path = parsed_url.path
        query = parse_qs(parsed_url.query)
        engine_param = query.get("engine", [None])[0]

        if path.startswith(async_prefix):
            scenario_id = path[len(async_prefix) :]
            if scenario_id not in SCENARIOS:
                self._json({"error": "unknown_scenario", "scenario_id": scenario_id}, HTTPStatus.NOT_FOUND)
                return
            
            cluster_alive = is_temporal_cluster_alive()
            if not engine_param or engine_param == "auto":
                effective_engine = "temporal-cluster" if cluster_alive else "temporal"
            else:
                effective_engine = engine_param

            if effective_engine == "temporal-cluster":
                engine_label = "Native Temporal Server Cluster (127.0.0.1:7233)"
                temporal_ui_url = "http://localhost:8233"
            elif effective_engine == "legacy":
                engine_label = "Legacy Python Orchestrator (Mock/In-Process)"
                temporal_ui_url = None
            else:
                engine_label = "Temporal.io Workflow Engine (In-Memory Simulation)"
                temporal_ui_url = None

            run_id = str(uuid.uuid4())
            with self.runs_lock:
                self.runs[run_id] = {
                    "run_id": run_id,
                    "scenario_id": scenario_id,
                    "status": "RUNNING",
                    "active_nodes": [],
                    "events": [],
                    "engine_info": {
                        "engine_type": effective_engine,
                        "engine_label": engine_label,
                        "is_temporal": effective_engine in ("temporal", "temporal-cluster"),
                        "is_cluster": effective_engine == "temporal-cluster",
                        "temporal_ui_url": temporal_ui_url,
                    },
                    "result": None,
                    "error": None,
                }
            threading.Thread(
                target=self._run_async,
                args=(run_id, scenario_id, effective_engine),
                name=f"poc-run-{run_id[:8]}",
                daemon=True,
            ).start()
            self._json({"run_id": run_id, "status": "RUNNING"}, HTTPStatus.ACCEPTED)
            return
        prefix = "/api/run/"
        if not path.startswith(prefix):
            self._json({"error": "not_found"}, HTTPStatus.NOT_FOUND)
            return
        scenario_id = path[len(prefix) :]
        if scenario_id not in SCENARIOS:
            self._json({"error": "unknown_scenario", "scenario_id": scenario_id}, HTTPStatus.NOT_FOUND)
            return
        try:
            orchestrator = self.get_orchestrator(engine=engine_param)
            result = orchestrator.run(scenario_id)
            self._json(result.to_dict())
        except Exception as exc:
            self._json({"error": "run_failed", "message": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)

    @classmethod
    def _run_async(cls, run_id: str, scenario_id: str, engine: Optional[str] = None) -> None:
        def observe(event: dict) -> None:
            with cls.runs_lock:
                run = cls.runs[run_id]
                run["events"].append(event)
                node_id = event["node_id"]
                if event["event"] == "NODE_STARTED" and node_id not in run["active_nodes"]:
                    run["active_nodes"].append(node_id)
                elif event["event"] == "NODE_COMPLETED" and node_id in run["active_nodes"]:
                    run["active_nodes"].remove(node_id)

        try:
            orchestrator = cls.get_orchestrator(step_delay_ms=300, engine=engine)
            result = orchestrator.run(scenario_id, observer=observe)
            with cls.runs_lock:
                cls.runs[run_id]["status"] = "COMPLETED"
                cls.runs[run_id]["active_nodes"] = []
                cls.runs[run_id]["result"] = result.to_dict()
        except Exception as exc:
            with cls.runs_lock:
                cls.runs[run_id]["status"] = "FAILED"
                cls.runs[run_id]["active_nodes"] = []
                cls.runs[run_id]["error"] = str(exc)


def serve(host: str = "127.0.0.1", port: int = 8080, db_path: str = "credit_agent.db") -> None:
    POCRequestHandler.db_path = db_path
    server = ThreadingHTTPServer((host, port), POCRequestHandler)
    print(f"CreditAgent POC (localDB: {db_path}): http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
