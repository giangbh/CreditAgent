from __future__ import annotations

import argparse
import json
import sys
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
    worker.add_argument("--count", type=int, default=CONFIG.TEMPORAL_WORKER_COUNT, help="Number of concurrent worker instances")

    load = sub.add_parser("load-test", help="run multi-threaded concurrent load benchmark")
    load.add_argument("-n", "--total", type=int, default=12, help="Total requests")
    load.add_argument("-c", "--concurrency", type=int, default=4, help="Concurrent workers")
    load.add_argument("-m", "--mode", choices=["api", "temporal"], default="api", help="Benchmark mode")
    load.add_argument("-u", "--url", default=f"http://{CONFIG.WEB_HOST}:{CONFIG.WEB_PORT}", help="Web Server URL")
    load.add_argument("-s", "--scenario", default=None, help="Specific scenario")
    load.add_argument("-d", "--dynamic", action="store_true", help="Generate unique synthetic loan dossiers for every request")
    load.add_argument("-a", "--archetype", choices=["HEALTHY_PRIME", "POLICY_EXCEPTION_TENOR", "SUSPICIOUS_AML", "WEAK_CASHFLOW", "INCOMPLETE_DOCS"], default=None, help="Specify risk archetype for synthetic generation")
    load.add_argument("--db-path", default=CONFIG.DB_PATH, help="Database path")
    load.add_argument("-o", "--output", type=Path, default=None, help="Output JSON report path")

    exp = sub.add_parser("explain", help="generate comprehensive 13-agent explainable summary for a case")
    exp.add_argument("-s", "--scenario", choices=SCENARIOS, default="approve_conditions", help="Scenario ID to run and explain")
    exp.add_argument("-c", "--case-id", type=str, default=None, help="Existing Case ID in DB to explain")
    exp.add_argument("--db-path", type=str, default=CONFIG.DB_PATH, help="Database path")
    exp.add_argument("--json", action="store_true", help="Output report as JSON")
    exp.add_argument("--html", type=Path, default=None, help="Export report to standalone HTML file")
    exp.add_argument("--markdown", type=Path, default=None, help="Export report to Markdown file")
    exp.add_argument("--llm", action="store_true", help="Use DeepSeek LLM to synthesize narrative underwriting report")
    exp.add_argument("--llm-api-key", type=str, default=None, help="DeepSeek API key override")
    exp.add_argument("--llm-model", type=str, default=None, help="DeepSeek model name override")
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
        asyncio.run(start_temporal_worker(target_host=args.target_host, task_queue=args.task_queue, worker_count=args.count))
        return 0
    if args.command == "load-test":
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
        from scripts.load_test import execute_load_test
        report = execute_load_test(
            mode=args.mode,
            target_url=args.url,
            total_requests=args.total,
            concurrency=args.concurrency,
            scenario_filter=args.scenario,
            dynamic_dossiers=args.dynamic,
            archetype=args.archetype,
            db_path=args.db_path,
        )
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(report.__dict__, f, ensure_ascii=False, indent=2)
            print(f"[+] Saved load test report to: {args.output}")
        return 0 if report.failed_requests == 0 else 1
    if args.command == "explain":
        from .explainer import CaseExplainer
        from .llm_synthesizer import DeepSeekCreditSynthesizer
        repo = StateRepository(db_path=args.db_path)
        if args.case_id:
            state = repo.load_case(args.case_id)
            if not state:
                print(f"[-] Case ID not found in database: {args.case_id}")
                return 1
        else:
            orchestrator = CreditOrchestrator(db_repository=repo)
            result = orchestrator.run(args.scenario)
            state = result.state

        if args.llm:
            synthesizer = DeepSeekCreditSynthesizer(api_key=args.llm_api_key, model=args.llm_model)
            memo = synthesizer.generate_credit_memo(state)
            print(memo)
            if args.html:
                args.html.parent.mkdir(parents=True, exist_ok=True)
                args.html.write_text(synthesizer.generate_credit_memo_html(state), encoding="utf-8")
                print(f"\n[+] Exported LLM HTML memo to: {args.html}")
            if args.markdown:
                args.markdown.parent.mkdir(parents=True, exist_ok=True)
                args.markdown.write_text(memo, encoding="utf-8")
                print(f"\n[+] Exported LLM Markdown memo to: {args.markdown}")
            return 0

        report = CaseExplainer.explain(state)
        if args.json:
            print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
        else:
            print(report.to_markdown())

        if args.html:
            args.html.parent.mkdir(parents=True, exist_ok=True)
            args.html.write_text(report.to_html(), encoding="utf-8")
            print(f"\n[+] Exported standalone HTML report to: {args.html}")
        if args.markdown:
            args.markdown.parent.mkdir(parents=True, exist_ok=True)
            args.markdown.write_text(report.to_markdown(), encoding="utf-8")
            print(f"\n[+] Exported Markdown report to: {args.markdown}")
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
