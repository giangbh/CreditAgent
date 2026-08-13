from __future__ import annotations

import html
import json
from pathlib import Path

from .orchestrator import RunResult


def write_json(result: RunResult, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")


def write_html(result: RunResult, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    state = result.state
    nodes = "".join(
        f"<li><b>{html.escape(node['node_id'])}</b> {html.escape(node['agent_name'])}"
        f"<span>{html.escape(', '.join(node['written_paths']))}</span></li>"
        for node in state.node_history
    )
    tools = "".join(
        f"<tr><td>{html.escape(call['tool_name'])}</td><td>{html.escape(call['status'])}</td></tr>"
        for call in state.tool_history
    )
    raw_json = html.escape(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    document = f"""<!doctype html>
<html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>CreditAgent POC - {html.escape(result.scenario_name)}</title>
<style>
body{{font:15px/1.5 system-ui;margin:0;background:#f4f7fb;color:#152033}}main{{max-width:1100px;margin:auto;padding:32px}}
.hero,.card{{background:white;border:1px solid #dce3ed;border-radius:14px;padding:22px;margin-bottom:18px;box-shadow:0 4px 18px #17345c0c}}
.badge{{display:inline-block;background:#e7f7ee;color:#17653b;padding:6px 10px;border-radius:999px;font-weight:700}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:16px}}h1{{margin:.2em 0}}h2{{font-size:18px}}
ol{{padding-left:22px}}li{{padding:7px}}li span{{display:block;color:#5b6574;font-size:13px}}table{{border-collapse:collapse;width:100%}}
td,th{{border-bottom:1px solid #e4e9f0;padding:8px;text-align:left}}pre{{white-space:pre-wrap;max-height:520px;overflow:auto;background:#111827;color:#d1fae5;padding:16px;border-radius:10px}}
</style></head><body><main>
<section class="hero"><span class="badge">{'PASS' if result.outcome_matches else 'CHECK'}</span><h1>{html.escape(result.scenario_name)}</h1>
<p>{html.escape(result.scenario_id)} · {result.duration_ms} ms · human final authority required</p></section>
<div class="grid"><section class="card"><h2>Expected</h2><p>{html.escape(result.expected_outcome)}</p></section>
<section class="card"><h2>Actual A13 opinion</h2><p><b>{html.escape(result.actual_outcome)}</b></p></section>
<section class="card"><h2>Approval Control</h2><p>{html.escape(state.control['status'])}</p><small>AI approve: false · AI disburse: false</small></section></div>
<section class="card"><h2>13-agent execution</h2><ol>{nodes}</ol></section>
<section class="card"><h2>Simulated backend calls</h2><table><thead><tr><th>Tool</th><th>Status</th></tr></thead><tbody>{tools}</tbody></table></section>
<section class="card"><h2>State and audit evidence</h2><details><summary>Open JSON</summary><pre>{raw_json}</pre></details></section>
</main></body></html>"""
    path.write_text(document, encoding="utf-8")


def write_index(results: list[RunResult], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    cards = "".join(
        f'<a class="card" href="{html.escape(result.scenario_id)}.html">'
        f'<span class="badge">{"PASS" if result.outcome_matches else "CHECK"}</span>'
        f'<h2>{html.escape(result.scenario_name)}</h2>'
        f'<p>{html.escape(result.actual_outcome)}</p>'
        f'<small>13 agents · {len(result.state.tool_history)} tools · {result.duration_ms} ms</small></a>'
        for result in results
    )
    document = f"""<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>CreditAgent POC Results</title><style>body{{font:15px/1.5 system-ui;margin:0;background:#f4f7fb;color:#152033}}main{{max-width:1100px;margin:auto;padding:36px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px}}.card{{text-decoration:none;color:inherit;background:white;border:1px solid #dce3ed;border-radius:14px;padding:20px;box-shadow:0 4px 18px #17345c0c}}
.card:hover{{border-color:#2563eb;transform:translateY(-1px)}}.badge{{background:#dcfce7;color:#166534;padding:4px 9px;border-radius:999px;font-size:12px;font-weight:700}}small{{color:#64748b}}</style></head>
<body><main><h1>CreditAgent POC Results</h1><p>Six reproducible scenarios exercising 13 bounded agents, simulated backend tools and deterministic approval control.</p><div class="grid">{cards}</div></main></body></html>"""
    (output_dir / "index.html").write_text(document, encoding="utf-8")
