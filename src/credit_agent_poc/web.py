from __future__ import annotations

import json
import threading
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from urllib.parse import parse_qs, urlparse

from .config import CONFIG
from .db import StateRepository
from .logger import audit_log
from .orchestrator import CreditOrchestrator
from .scenarios import SCENARIOS, scenario_catalog
from .tools.simulated.mock_server import MockBackendServiceHandler


def is_temporal_cluster_alive(host: Optional[str] = None, port: Optional[int] = None) -> bool:
    import socket
    target_host = host or CONFIG.TEMPORAL_HOST
    target_port = port or CONFIG.TEMPORAL_PORT
    try:
        with socket.create_connection((target_host, target_port), timeout=1.5):
            return True
    except Exception:
        return False


class POCRequestHandler(BaseHTTPRequestHandler):
    db_path: str = CONFIG.DB_PATH
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

        if path.startswith("/api/v1/"):
            status_code, response_data = MockBackendServiceHandler.handle_request(path, method="GET")
            self._json(response_data, HTTPStatus(status_code))
            return

        if path == "/api/scenarios":
            self._json(scenario_catalog())
            return
        if path == "/api/engine-info":
            cluster_alive = is_temporal_cluster_alive()
            self._json({
                "cluster_alive": cluster_alive,
                "active_engine": "temporal",
                "engine_label": f"Native Temporal Server Cluster ({CONFIG.TEMPORAL_TARGET_HOST})" if cluster_alive else f"Native Temporal Server Engine ({CONFIG.TEMPORAL_TARGET_HOST})",
                "temporal_ui_url": CONFIG.TEMPORAL_UI_URL,
            })
            return
        if path == "/api/health":
            cluster_alive = is_temporal_cluster_alive()
            self._json({
                "status": "ok",
                "service": "credit-agent-poc",
                "db": self.db_path,
                "temporal_cluster_alive": cluster_alive,
                "active_engine": "temporal",
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
        if path.startswith("/api/v1/"):
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length) if content_length > 0 else b"{}"
            try:
                data = json.loads(body) if body else {}
            except ValueError:
                data = {}
            status_code, response_data = MockBackendServiceHandler.handle_request(path, method="POST", body_dict=data)
            self._json(response_data, HTTPStatus(status_code))
            return

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
            effective_engine = "temporal"
            engine_label = f"Native Temporal Server Cluster ({CONFIG.TEMPORAL_TARGET_HOST})" if cluster_alive else f"Native Temporal Server Engine ({CONFIG.TEMPORAL_TARGET_HOST})"
            temporal_ui_url = CONFIG.TEMPORAL_UI_URL

            run_id = str(uuid.uuid4())
            with self.runs_lock:
                self.runs[run_id] = {
                    "run_id": run_id,
                    "scenario_id": scenario_id,
                    "status": "RUNNING",
                    "active_nodes": [],
                    "events": [],
                    "engine_info": {
                        "engine_type": "temporal",
                        "engine_label": engine_label,
                        "is_temporal": True,
                        "is_cluster": cluster_alive,
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

        trace_id = f"tr-{run_id}"
        case_id = f"CASE-{scenario_id.upper()}-{run_id[:6].upper()}"
        audit_log("API_RUN_REQUEST_STARTED", "WEB_SERVER", trace_id, case_id, details={"run_id": run_id, "scenario_id": scenario_id, "engine": engine})
        try:
            db_repo = StateRepository(cls.db_path)
            db_repo.log_audit_event(run_id, AuditEvent(event="api_run_request_started", node_id="WEB_SERVER", details={"scenario_id": scenario_id, "engine": engine}))
        except Exception:
            pass

        try:
            orchestrator = cls.get_orchestrator(step_delay_ms=0, engine=engine)
            result = orchestrator.run(scenario_id, observer=observe)
            case_id = result.state.case_id
            with cls.runs_lock:
                cls.runs[run_id]["status"] = "COMPLETED"
                cls.runs[run_id]["active_nodes"] = []
                cls.runs[run_id]["result"] = result.to_dict()
            audit_log("API_RUN_REQUEST_COMPLETED", "WEB_SERVER", trace_id, case_id, details={"run_id": run_id, "outcome": result.actual_outcome})
            try:
                db_repo = StateRepository(cls.db_path)
                db_repo.log_audit_event(run_id, AuditEvent(event="api_run_request_completed", node_id="WEB_SERVER", details={"case_id": case_id, "outcome": result.actual_outcome}))
            except Exception:
                pass
        except Exception as exc:
            with cls.runs_lock:
                cls.runs[run_id]["status"] = "FAILED"
                cls.runs[run_id]["active_nodes"] = []
                cls.runs[run_id]["error"] = str(exc)
            audit_log("API_RUN_REQUEST_FAILED", "WEB_SERVER", trace_id, case_id, level="ERROR", details={"run_id": run_id, "error": str(exc)})
            try:
                db_repo = StateRepository(cls.db_path)
                db_repo.log_audit_event(run_id, AuditEvent(event="api_run_request_failed", node_id="WEB_SERVER", details={"error": str(exc)}))
            except Exception:
                pass


def _start_background_temporal_worker(
    host: str = CONFIG.TEMPORAL_TARGET_HOST,
    task_queue: str = CONFIG.TEMPORAL_TASK_QUEUE,
    worker_count: int = CONFIG.TEMPORAL_WORKER_COUNT,
) -> None:
    """Khởi chạy Worker Pool Temporal thường trực dưới nền khi Web Server chạy."""
    def _worker_thread():
        async def _run():
            try:
                from .workflow import start_temporal_worker
                if is_temporal_cluster_alive(host):
                    await start_temporal_worker(target_host=host, task_queue=task_queue, worker_count=worker_count)
            except Exception:
                pass

        try:
            asyncio.run(_run())
        except Exception:
            pass

    threading.Thread(target=_worker_thread, name="temporal-bg-worker", daemon=True).start()


def serve(host: Optional[str] = None, port: Optional[int] = None, db_path: Optional[str] = None) -> None:
    target_host = host or CONFIG.WEB_HOST
    target_port = port or CONFIG.WEB_PORT
    target_db = db_path or CONFIG.DB_PATH
    POCRequestHandler.db_path = target_db
    server = ThreadingHTTPServer((target_host, target_port), POCRequestHandler)
    print(f"CreditAgent POC (localDB: {target_db}): http://{target_host}:{target_port}")
    _start_background_temporal_worker()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
