from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import List, Optional

from .config import CONFIG
from .db import StateRepository
from .model import OpenAICompatibleModel, ScenarioModel
from .orchestrator import CreditOrchestrator
from .report import write_html, write_index, write_json
from .scenarios import SCENARIOS, scenario_catalog
from .web import serve


def _model(name: str):
    return ScenarioModel() if name == "mock" else OpenAICompatibleModel()


def _print_result(result) -> None:
    mark = "PASS" if result.outcome_matches else "MISMATCH"
    print(f"[{mark}] {result.scenario_id}")
    print(f"  expected: {result.expected_outcome}")
    print(f"  actual:   {result.actual_outcome}")
    print(f"  control:  {result.state.control['status']}")
    print(f"  agents:   {len(result.state.node_history)} | tools: {len(result.state.tool_history)} | {result.duration_ms} ms")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CreditAgent multi-agent orchestration POC")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="list demo scenarios")

    run = sub.add_parser("run", help="run one scenario")
    run.add_argument("--scenario", choices=SCENARIOS, default="approve_conditions")
    run.add_argument("--model", choices=["mock", "openai-compatible"], default="mock")
    run.add_argument("--engine", choices=["temporal", "temporal-cluster", "legacy"], default="temporal")
    run.add_argument("--db-path", type=str, default=CONFIG.DB_PATH, help="SQLite localDB database path")
    run.add_argument("--json", action="store_true", help="print the full run as JSON")
    run.add_argument("--output-dir", type=Path, help="write JSON and HTML reports")

    run_all = sub.add_parser("run-all", help="run all scenarios")
    run_all.add_argument("--model", choices=["mock", "openai-compatible"], default="mock")
    run_all.add_argument("--engine", choices=["temporal", "temporal-cluster", "legacy"], default="temporal")
    run_all.add_argument("--db-path", type=str, default=CONFIG.DB_PATH, help="SQLite localDB database path")
    run_all.add_argument("--output-dir", type=Path, default=Path("demo-output"))

    web = sub.add_parser("serve", help="start the local review UI")
    web.add_argument("--host", default=CONFIG.WEB_HOST)
    web.add_argument("--port", type=int, default=CONFIG.WEB_PORT)
    web.add_argument("--db-path", type=str, default=CONFIG.DB_PATH, help="SQLite localDB database path")

    worker = sub.add_parser("worker", help="start a native Temporal Worker process")
    worker.add_argument("--target-host", default=CONFIG.TEMPORAL_TARGET_HOST, help="Temporal Server cluster host")
    worker.add_argument("--task-queue", default=CONFIG.TEMPORAL_TASK_QUEUE, help="Temporal task queue name")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "list":
        print(json.dumps(scenario_catalog(), ensure_ascii=False, indent=2))
        return 0
    if args.command == "serve":
        serve(args.host, args.port, db_path=args.db_path)
        return 0
    if args.command == "worker":
        import asyncio
        from .workflow import start_temporal_worker
        asyncio.run(start_temporal_worker(target_host=args.target_host, task_queue=args.task_queue))
        return 0

    repo = StateRepository(db_path=args.db_path)
    orchestrator = CreditOrchestrator(model=_model(args.model), db_repository=repo, engine=args.engine)
    if args.command == "run":
        result = orchestrator.run(args.scenario)
        if args.json:
            print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        else:
            _print_result(result)
        if args.output_dir:
            write_json(result, args.output_dir / f"{result.scenario_id}.json")
            write_html(result, args.output_dir / f"{result.scenario_id}.html")
        return 0 if result.outcome_matches else 1

    results = orchestrator.run_all()
    for result in results:
        _print_result(result)
        write_json(result, args.output_dir / f"{result.scenario_id}.json")
        write_html(result, args.output_dir / f"{result.scenario_id}.html")
    write_index(results, args.output_dir)
    passed = sum(result.outcome_matches for result in results)
    print(f"\nSummary: {passed}/{len(results)} scenarios matched; reports: {args.output_dir}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
