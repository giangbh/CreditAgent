#!/usr/bin/env python3
"""Enterprise Load Testing Tool for CreditAgent Multi-Agent Orchestration POC.

Supports:
- HTTP API Async Mode (Simulating multiple concurrent loan officers / frontend clients)
- Direct Temporal Workflow Engine Mode (High-throughput native distributed orchestration)
- Latency percentiles (P50, P90, P95, P99), Throughput (TPS), and Control Gate integrity checks.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import random
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


SCENARIOS = [
    "approve_conditions",
    "escalate_policy_exception",
    "reject_missing_evidence",
    "escalate_circular_funds",
    "reject_weak_cashflow_high_collateral",
    "reject_tool_failure",
]


@dataclass
class CaseExecutionResult:
    index: int
    scenario_id: str
    run_id: str
    case_id: str
    success: bool
    duration_ms: float
    outcome: str
    control_status: str
    error: Optional[str] = None


@dataclass
class LoadTestReport:
    timestamp: str
    mode: str
    target: str
    total_requests: int
    concurrency: int
    successful_requests: int
    failed_requests: int
    total_time_seconds: float
    throughput_tps: float
    min_latency_ms: float
    mean_latency_ms: float
    p50_latency_ms: float
    p90_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    max_latency_ms: float
    outcomes_distribution: Dict[str, int] = field(default_factory=dict)
    scenario_distribution: Dict[str, int] = field(default_factory=dict)
    control_status_distribution: Dict[str, int] = field(default_factory=dict)


def _http_post(url: str, data: Optional[dict] = None, timeout: float = 30.0) -> dict:
    body = json.dumps(data or {}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": "CreditAgent-LoadTester/1.0"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _http_get(url: str, timeout: float = 30.0) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "CreditAgent-LoadTester/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def run_http_case(
    index: int,
    base_url: str,
    scenario_input: Any,
    poll_interval_sec: float = 0.4,
    max_wait_sec: float = 120.0,
) -> CaseExecutionResult:
    start_time = time.perf_counter()
    if isinstance(scenario_input, dict):
        post_url = f"{base_url.rstrip('/')}/api/run-custom"
        post_data = scenario_input
        scenario_id = scenario_input.get("scenario_id", f"syn_{index}")
    else:
        scenario_id = str(scenario_input)
        post_url = f"{base_url.rstrip('/')}/api/run-async/{scenario_id}"
        post_data = {}

    try:
        init_resp = _http_post(post_url, data=post_data, timeout=15.0)
        run_id = init_resp.get("run_id", "")
        if not run_id:
            raise ValueError(f"No run_id returned by server: {init_resp}")

        # Poll run status until COMPLETED or FAILED
        status_url = f"{base_url.rstrip('/')}/api/run-status/{run_id}"
        deadline = start_time + max_wait_sec
        last_state = {}

        while time.perf_counter() < deadline:
            time.sleep(poll_interval_sec)
            status_resp = _http_get(status_url, timeout=10.0)
            status = status_resp.get("status", "")
            if status == "COMPLETED":
                dur = (time.perf_counter() - start_time) * 1000.0
                res = status_resp.get("result", {})
                state = res.get("state", {})
                outcome = res.get("actual_outcome", "UNKNOWN")
                control_st = state.get("control", {}).get("status", "UNKNOWN")
                case_id = state.get("case_id", "UNKNOWN")
                return CaseExecutionResult(
                    index=index,
                    scenario_id=scenario_id,
                    run_id=run_id,
                    case_id=case_id,
                    success=True,
                    duration_ms=dur,
                    outcome=outcome,
                    control_status=control_st,
                )
            elif status == "FAILED":
                dur = (time.perf_counter() - start_time) * 1000.0
                err = status_resp.get("error", "Execution failed")
                return CaseExecutionResult(
                    index=index,
                    scenario_id=scenario_id,
                    run_id=run_id,
                    case_id="N/A",
                    success=False,
                    duration_ms=dur,
                    outcome="FAILED",
                    control_status="ERROR",
                    error=err,
                )

        # Timeout reached
        dur = (time.perf_counter() - start_time) * 1000.0
        return CaseExecutionResult(
            index=index,
            scenario_id=scenario_id,
            run_id=run_id,
            case_id="TIMEOUT",
            success=False,
            duration_ms=dur,
            outcome="TIMEOUT",
            control_status="TIMEOUT",
            error=f"Timeout after {max_wait_sec}s",
        )
    except Exception as exc:
        dur = (time.perf_counter() - start_time) * 1000.0
        return CaseExecutionResult(
            index=index,
            scenario_id=scenario_id,
            run_id="N/A",
            case_id="ERROR",
            success=False,
            duration_ms=dur,
            outcome="ERROR",
            control_status="ERROR",
            error=str(exc),
        )


def run_direct_temporal_case(
    index: int,
    scenario_id: str,
    db_path: str = "credit_agent.db",
) -> CaseExecutionResult:
    start_time = time.perf_counter()
    try:
        from credit_agent_poc.db import StateRepository
        from credit_agent_poc.orchestrator import CreditOrchestrator

        repo = StateRepository(db_path=db_path)
        orchestrator = CreditOrchestrator(db_repository=repo, engine="temporal")
        result = orchestrator.run(scenario_id)
        dur = (time.perf_counter() - start_time) * 1000.0
        return CaseExecutionResult(
            index=index,
            scenario_id=scenario_id,
            run_id=result.state.run_id,
            case_id=result.state.case_id,
            success=bool(result.state and result.state.control and result.state.control.get("status") != "ERROR"),
            duration_ms=dur,
            outcome=result.actual_outcome,
            control_status=result.state.control.get("status", "UNKNOWN"),
        )
    except Exception as exc:
        dur = (time.perf_counter() - start_time) * 1000.0
        return CaseExecutionResult(
            index=index,
            scenario_id=scenario_id,
            run_id="N/A",
            case_id="ERROR",
            success=False,
            duration_ms=dur,
            outcome="ERROR",
            control_status="ERROR",
            error=str(exc),
        )


def calculate_percentiles(values: List[float]) -> Dict[str, float]:
    if not values:
        return {"min": 0.0, "mean": 0.0, "p50": 0.0, "p90": 0.0, "p95": 0.0, "p99": 0.0, "max": 0.0}
    s = sorted(values)
    n = len(s)

    def _pct(p: float) -> float:
        idx = int(round(p * (n - 1)))
        return s[min(max(idx, 0), n - 1)]

    return {
        "min": round(s[0], 2),
        "mean": round(sum(s) / n, 2),
        "p50": round(_pct(0.50), 2),
        "p90": round(_pct(0.90), 2),
        "p95": round(_pct(0.95), 2),
        "p99": round(_pct(0.99), 2),
        "max": round(s[-1], 2),
    }


def print_progress_bar(completed: int, total: int, prefix: str = "", length: int = 30) -> None:
    percent = f"{100 * (completed / float(total)):.1f}"
    filled = int(length * completed // total)
    bar = "█" * filled + "░" * (length - filled)
    sys.stdout.write(f"\r{prefix} |{bar}| {completed}/{total} ({percent}%) ")
    sys.stdout.flush()
    if completed >= total:
        sys.stdout.write("\n")


def execute_load_test(
    mode: str = "api",
    target_url: str = "http://127.0.0.1:8080",
    total_requests: int = 20,
    concurrency: int = 4,
    scenario_filter: Optional[str] = None,
    dynamic_dossiers: bool = False,
    archetype: Optional[str] = None,
    db_path: str = "credit_agent.db",
) -> LoadTestReport:
    print("\n" + "=" * 70)
    print(" 🚀 CREDITAGENT POC LOAD & STRESS TEST BENCHMARK")
    print("=" * 70)
    print(f" • Mode:             {mode.upper()}")
    print(f" • Target:           {target_url if mode == 'api' else 'Direct Temporal Engine'}")
    print(f" • Total Requests:   {total_requests}")
    print(f" • Concurrency:      {concurrency} concurrent workers")
    if dynamic_dossiers:
        print(f" • Dossier Mode:     ⚡ DYNAMIC SYNTHETIC (Archetype: {archetype or 'RANDOM_MIX'})")
    else:
        print(f" • Scenario:         {scenario_filter or 'Random Mix across all 6 static scenarios'}")
    print("=" * 70 + "\n")

    # Prepare list of scenarios
    case_scenarios = []
    if dynamic_dossiers:
        from dataclasses import asdict
        from credit_agent_poc.dossier_generator import SyntheticDossierGenerator
        syn_scenarios = SyntheticDossierGenerator.generate_batch(count=total_requests, archetype=archetype)
        for i, sc in enumerate(syn_scenarios):
            inp = asdict(sc) if mode == "api" else sc.scenario_id
            case_scenarios.append((i + 1, inp))
    else:
        for i in range(total_requests):
            if scenario_filter and scenario_filter in SCENARIOS:
                sc = scenario_filter
            else:
                sc = SCENARIOS[i % len(SCENARIOS)]
            case_scenarios.append((i + 1, sc))

    results: List[CaseExecutionResult] = []
    start_total_time = time.perf_counter()
    completed_count = 0

    print_progress_bar(0, total_requests, prefix="Progress:")

    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = []
        for idx, sc in case_scenarios:
            if mode == "api":
                f = executor.submit(run_http_case, idx, target_url, sc)
            else:
                f = executor.submit(run_direct_temporal_case, idx, sc, db_path)
            futures.append(f)

        for future in concurrent.futures.as_completed(futures):
            res = future.result()
            results.append(res)
            completed_count += 1
            print_progress_bar(completed_count, total_requests, prefix="Progress:")

    total_duration_sec = time.perf_counter() - start_total_time

    # Compute statistics
    successful = [r for r in results if r.success]
    failed = [r for r in results if not r.success]
    latencies = [r.duration_ms for r in successful]
    pcts = calculate_percentiles(latencies)

    outcomes_dist: Dict[str, int] = {}
    scenario_dist: Dict[str, int] = {}
    control_dist: Dict[str, int] = {}

    for r in results:
        outcomes_dist[r.outcome] = outcomes_dist.get(r.outcome, 0) + 1
        scenario_dist[r.scenario_id] = scenario_dist.get(r.scenario_id, 0) + 1
        control_dist[r.control_status] = control_dist.get(r.control_status, 0) + 1

    throughput_tps = round(len(successful) / max(total_duration_sec, 0.001), 2)

    report = LoadTestReport(
        timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
        mode=mode,
        target=target_url if mode == "api" else "TemporalWorkflowEngine",
        total_requests=total_requests,
        concurrency=concurrency,
        successful_requests=len(successful),
        failed_requests=len(failed),
        total_time_seconds=round(total_duration_sec, 2),
        throughput_tps=throughput_tps,
        min_latency_ms=pcts["min"],
        mean_latency_ms=pcts["mean"],
        p50_latency_ms=pcts["p50"],
        p90_latency_ms=pcts["p90"],
        p95_latency_ms=pcts["p95"],
        p99_latency_ms=pcts["p99"],
        max_latency_ms=pcts["max"],
        outcomes_distribution=outcomes_dist,
        scenario_distribution=scenario_dist,
        control_status_distribution=control_dist,
    )

    _print_report_summary(report, results, db_path)
    return report


def _print_report_summary(
    report: LoadTestReport, results: List[CaseExecutionResult], db_path: str = "credit_agent.db"
) -> None:
    print("\n" + "=" * 70)
    print(" 📊 LOAD TEST EXECUTION SUMMARY REPORT")
    print("=" * 70)
    print(f" • Total Completed:  {report.total_requests} cases ({report.successful_requests} passed, {report.failed_requests} failed)")
    print(f" • Success Rate:     {round(100 * report.successful_requests / max(report.total_requests, 1), 2)}%")
    print(f" • Total Wall Clock: {report.total_time_seconds}s")
    print(f" • System TPS:       {report.throughput_tps} loans/sec")
    print("-" * 70)
    print(" ⏱️  LATENCY PERCENTILES (End-to-End multi-agent approval time):")
    print(f"   - Min Latency:    {report.min_latency_ms:.1f} ms")
    print(f"   - Mean Latency:   {report.mean_latency_ms:.1f} ms")
    print(f"   - P50 (Median):   {report.p50_latency_ms:.1f} ms")
    print(f"   - P90:            {report.p90_latency_ms:.1f} ms")
    print(f"   - P95:            {report.p95_latency_ms:.1f} ms")
    print(f"   - P99:            {report.p99_latency_ms:.1f} ms")
    print(f"   - Max Latency:    {report.max_latency_ms:.1f} ms")
    print("-" * 70)
    print(" ⚖️  CREDIT OUTCOMES BREAKDOWN:")
    for out, count in sorted(report.outcomes_distribution.items()):
        print(f"   - {out:<35}: {count:>4} cases")
    print("-" * 70)
    print(" 🛡️  CONTROL GATE DECISIONS:")
    for ctrl, count in sorted(report.control_status_distribution.items()):
        print(f"   - Control Gate Status '{ctrl}': {count:>4} cases")

    # DB Integrity Check
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM credit_cases")
        cases_count = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM audit_events")
        audit_count = cur.fetchone()[0]
        conn.close()
        print("-" * 70)
        print(" 💾 DATABASE PERSISTENCE STATUS:")
        print(f"   - Rows in `credit_cases`:  {cases_count}")
        print(f"   - Rows in `audit_events`:  {audit_count}")
    except Exception:
        pass

    print("=" * 70 + "\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CreditAgent Load Testing & Benchmarking CLI")
    parser.add_argument("-n", "--total", type=int, default=12, help="Total number of loan approval cases to run")
    parser.add_argument("-c", "--concurrency", type=int, default=4, help="Number of concurrent client workers")
    parser.add_argument("-m", "--mode", choices=["api", "temporal"], default="api", help="Load test mode (HTTP API or direct Temporal)")
    parser.add_argument("-u", "--url", default="http://127.0.0.1:8080", help="Web Server URL (for API mode)")
    parser.add_argument("-s", "--scenario", choices=SCENARIOS, default=None, help="Fix a specific scenario (default: random mix)")
    parser.add_argument("-d", "--dynamic", action="store_true", help="Generate unique synthetic loan dossiers for every request")
    parser.add_argument(
        "-a", "--archetype",
        choices=["HEALTHY_PRIME", "POLICY_EXCEPTION_TENOR", "SUSPICIOUS_AML", "WEAK_CASHFLOW", "INCOMPLETE_DOCS"],
        default=None,
        help="Specify risk archetype for synthetic generation",
    )
    parser.add_argument("--db-path", default="credit_agent.db", help="SQLite database path")
    parser.add_argument("-o", "--output", type=Path, default=None, help="Save report to JSON file")
    return parser


def main() -> int:
    args = build_parser().parse_args()
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
            json.dump(asdict(report), f, ensure_ascii=False, indent=2)
        print(f"[+] Saved load test JSON report to: {args.output}")

    return 0 if report.failed_requests == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
