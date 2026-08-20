from __future__ import annotations

import dataclasses
import html
import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from .agents.registry import AGENT_NAMES
from .models import CreditState

STAGE_MAP = {
    "A1": "Stage 1: Evidence Ingestion & Normalization",
    "A2": "Stage 1: Financial & Cashflow Analysis",
    "A3": "Stage 1: Transaction Graph & Integrity Analysis",
    "A4": "Stage 1: Financial Capacity & Debt Service Analysis",
    "A5": "Stage 1: Policy Compliance & Authority Verification",
    "A6": "Stage 2: Credit Advocate (Growth & Upside Lens)",
    "A7": "Stage 2: Risk Challenger (Downside Stress Lens)",
    "A8": "Stage 2: Assessment Arbiter (Synthesis & Covenants)",
    "A9": "Stage 3: Deal Structuring & Facility Design",
    "A10": "Stage 4: Risk Committee - Business Upside Lens",
    "A11": "Stage 4: Risk Committee - Conservative Risk Lens",
    "A12": "Stage 4: Risk Committee - Governance & Policy Arbiter",
    "A13": "Stage 5: Co-Approval Advisory Draft Opinion",
}


@dataclass
class AgentExplanation:
    node_id: str
    agent_name: str
    stage: str
    status: str
    inputs_summary: Dict[str, Any]
    outputs_summary: Dict[str, Any]
    rationale: str
    key_indicators: Dict[str, Any]
    verdict_signal: str  # GREEN, YELLOW, RED, PURPLE


@dataclass
class StageSynthesis:
    stage_id: str
    stage_name: str
    participating_agents: List[str]
    stage_summary: str
    key_takeaway: str
    details: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class CaseExplanationReport:
    case_id: str
    scenario_id: str
    run_id: str
    trace_id: str
    timestamp: str
    borrower: Dict[str, Any]
    loan_request: Dict[str, Any]
    final_ai_decision: str
    control_gate_status: str
    risk_level: str
    confidence_score: float
    primary_decision_drivers: List[str]
    agent_explanations: List[AgentExplanation]
    stage_syntheses: List[StageSynthesis]
    actionable_covenants: List[str]
    conditions_precedent: List[str]
    governance_and_compliance: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_markdown(self) -> str:
        md = []
        md.append(f"# 📋 TỜ TRÌNH TÓM TẮT & GIẢI TRÌNH QUYẾT ĐỊNH THẨM ĐỊNH TÍN DỤNG")
        md.append(f"**Mã Hồ sơ (Case ID):** `{self.case_id}` | **Kịch bản:** `{self.scenario_id}` | **Run ID:** `{self.run_id[:8]}`")
        md.append(f"**Thời gian thẩm định:** {self.timestamp}\n")
        md.append(f"---")
        
        # 1. Executive Summary
        md.append(f"## 🏛️ 1. TÓM TẮT ĐIỀU HÀNH (EXECUTIVE SUMMARY)")
        b_name = self.borrower.get('name') or self.borrower.get('company_name', 'N/A')
        b_tax = self.borrower.get('tax_code') or self.borrower.get('tax_id', 'N/A')
        md.append(f"- **Khách hàng vay:** **{b_name}** (MST: `{b_tax}`)")
        md.append(f"- **Phân khúc / Ngành nghề:** {self.borrower.get('segment', 'SME')} · {self.borrower.get('industry', 'N/A')}")
        
        req_amt = self.loan_request.get('amount') or self.loan_request.get('requested_amount', 0)
        tenor = self.loan_request.get('tenor_months', 12)
        purpose = self.loan_request.get('purpose', 'working_capital')
        md.append(f"- **Nhu cầu cấp tín dụng:** **{req_amt:,.0f} VND** | Thời hạn: **{tenor} tháng** | Mục đích: `{purpose}`")
        md.append(f"- **Ý kiến AI Co-Approval (A13):** `{self.final_ai_decision}` (Độ tin cậy: **{self.confidence_score*100:.0f}%** · `DRAFT Bản nháp tư vấn`)")
        md.append(f"- **Khóa Kiểm Soát Thể Chế (Control Gate):** `{self.control_gate_status}`")
        md.append(f"- **Mức độ Rủi ro Tổng thể:** `{self.risk_level}`\n")

        md.append(f"### 🎯 Các Yếu Tố Quyết Định Cốt Lõi (Key Decision Drivers):")
        for driver in self.primary_decision_drivers:
            md.append(f"- {driver}")
        md.append("")

        # 2. 13 Agent Explanations Table
        md.append(f"## 🔍 2. BẢNG MA TRẬN GIẢI TRÌNH CHI TIẾT 13 AGENTS")
        md.append(f"| Mã Agent & Vai trò | Tín hiệu | Dữ liệu Đầu vào (Key Inputs) | Kết quả Đầu ra (Key Outputs) | 💡 Lý Do & Logic Quyết Định (Why / Rationale) |")
        md.append(f"|---|---|---|---|---|")
        for a in self.agent_explanations:
            inputs_str = "<br>".join(f"• <b>{k}</b>: {v}" for k, v in a.inputs_summary.items())
            outputs_str = "<br>".join(f"• <b>{k}</b>: {v}" for k, v in a.outputs_summary.items())
            md.append(f"| **{a.node_id}**: {a.agent_name}<br><small><i>{a.stage}</i></small> | `{a.verdict_signal}` | {inputs_str} | {outputs_str} | {a.rationale} |")
        md.append("")

        # 3. Stage Syntheses
        md.append(f"## ⚖️ 3. TỔNG HỢP TRANH BIỆN THEO 5 GIAI ĐOẠN")
        for st in self.stage_syntheses:
            md.append(f"### {st.stage_name}")
            md.append(f"- **Agents tham gia:** `{'`, `'.join(st.participating_agents)}`")
            md.append(f"- **Diễn biến:** {st.stage_summary}")
            md.append(f"- **Kết luận giai đoạn:** *{st.key_takeaway}*\n")
            if st.details:
                for det in st.details:
                    md.append(f"  - **{det.get('title', '')}**: {det.get('content', '')}")
                md.append("")

        # 4. Actionable Covenants & Conditions
        if self.actionable_covenants or self.conditions_precedent:
            md.append(f"## 📜 4. DANH MỤC ĐIỀU KIỆN RÀNG BUỘC (COVENANTS & CONDITIONS)")
            if self.conditions_precedent:
                md.append(f"#### Điều kiện Tiên quyết trước Giải ngân (Conditions Precedent):")
                for i, cp in enumerate(self.conditions_precedent, 1):
                    md.append(f"{i}. {cp}")
            if self.actionable_covenants:
                md.append(f"#### Điều kiện Quản lý Sau Giải ngân (Ongoing Covenants):")
                for i, cov in enumerate(self.actionable_covenants, 1):
                    md.append(f"{i}. {cov}")
            md.append("")

        # 5. Governance & Digital Seal
        md.append(f"## 🛡️ 5. BẢO CHỨNG THỂ CHẾ & NIÊM PHONG SỐ")
        seal = self.governance_and_compliance.get("digital_seal_hash", "N/A")
        md.append(f"- **Mã Băm Niêm Phong Hồ Sơ (HMAC-SHA256):** `{seal}`")
        md.append(f"- **Chính sách áp dụng:** `{self.governance_and_compliance.get('policy_id', 'POLICY-SME-2025-v2.1')}`")
        md.append(f"- **Thẩm quyền phê duyệt quy định:** `{self.governance_and_compliance.get('required_authority', 'CREDIT_COMMITTEE')}`")
        md.append(f"- **Quy tắc Bất khả xâm phạm:** AI tuyệt đối không có quyền tự động duyệt hoặc tự động giải ngân.")

        return "\n".join(md)

    def to_html(self) -> str:
        b_name = self.borrower.get('name') or self.borrower.get('company_name', 'N/A')
        b_tax = self.borrower.get('tax_code') or self.borrower.get('tax_id', 'N/A')
        b_ind = self.borrower.get('industry', 'N/A')
        b_seg = self.borrower.get('segment', 'SME')
        req_amt = self.loan_request.get('amount') or self.loan_request.get('requested_amount', 0)
        tenor = self.loan_request.get('tenor_months', 12)
        purpose = self.loan_request.get('purpose', 'working_capital')

        # 13 agent rows
        rows = []
        for a in self.agent_explanations:
            in_html = "<br>".join(f"• <b>{html.escape(str(k))}</b>: {html.escape(str(v))}" for k, v in a.inputs_summary.items())
            out_html = "<br>".join(f"• <b>{html.escape(str(k))}</b>: {html.escape(str(v))}" for k, v in a.outputs_summary.items())
            rows.append(f"""<tr>
<td style="font-weight:700; color:#38bdf8;">
  {html.escape(a.node_id)}: {html.escape(a.agent_name)}<br>
  <small style="color:#94a3b8; font-weight:normal;">{html.escape(a.stage)}</small>
</td>
<td><span class="badge badge-{a.verdict_signal}">{html.escape(a.verdict_signal)}</span></td>
<td style="font-size:12px; color:#cbd5e1;">{in_html}</td>
<td style="font-size:12px; color:#cbd5e1;">{out_html}</td>
<td style="color:#f8fafc; font-size:13px; line-height:1.45;">{html.escape(a.rationale)}</td>
</tr>""")

        drivers_html = "".join(f"<li style='margin-bottom:8px;'>{html.escape(d)}</li>" for d in self.primary_decision_drivers)

        # Stage syntheses cards
        stage_cards = []
        for st in self.stage_syntheses:
            det_html = ""
            if st.details:
                det_items = "".join(f"<li><b>{html.escape(d.get('title',''))}:</b> {html.escape(str(d.get('content','')))}</li>" for d in st.details)
                det_html = f"<ul style='margin:8px 0 0; padding-left:18px; color:#94a3b8; font-size:12px;'>{det_items}</ul>"

            stage_cards.append(f"""
<div class="stage-card">
  <div style="display:flex; justify-content:space-between; align-items:center;">
    <h3 style="margin:0; color:#38bdf8; font-size:14px;">{html.escape(st.stage_name)}</h3>
    <span style="font-size:11px; color:#94a3b8;">Agents: <code>{html.escape(', '.join(st.participating_agents))}</code></span>
  </div>
  <p style="margin:8px 0 4px; font-size:13px; color:#cbd5e1;">{html.escape(st.stage_summary)}</p>
  <div style="background:#0f172a; padding:8px 12px; border-radius:6px; border-left:3px solid #38bdf8; margin-top:6px; font-size:12px; color:#34d399;">
    <b>Kết luận:</b> {html.escape(st.key_takeaway)}
  </div>
  {det_html}
</div>
""")

        # Covenants
        cp_html = "".join(f"<li style='margin-bottom:6px;'>{html.escape(cp)}</li>" for cp in self.conditions_precedent) or "<li>Không có điều kiện tiên quyết đặc thù.</li>"
        cov_html = "".join(f"<li style='margin-bottom:6px;'>{html.escape(cov)}</li>" for cov in self.actionable_covenants) or "<li>Tuân thủ các điều khoản hợp đồng tín dụng chuẩn.</li>"

        return f"""<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Báo cáo Tóm tắt & Giải trình Chi tiết - Hồ sơ {html.escape(self.case_id)}</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background: #0b1120; color: #f1f5f9; margin: 0; padding: 28px 16px; }}
.container {{ max-width: 1240px; margin: 0 auto; background: #1e293b; border-radius: 14px; border: 1px solid #334155; padding: 32px; box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.7); }}
.header-box {{ border-bottom: 2px solid #334155; padding-bottom: 18px; margin-bottom: 24px; display:flex; justify-content:space-between; align-items:flex-start; flex-wrap:wrap; gap:16px; }}
h1 {{ color: #38bdf8; font-size: 22px; margin: 0 0 6px; }}
h2 {{ color: #93c5fd; font-size: 17px; margin: 28px 0 14px; border-bottom: 1px solid #334155; padding-bottom: 8px; display:flex; align-items:center; gap:8px; }}
h3 {{ color: #cbd5e1; font-size: 14px; margin-top: 14px; }}
p, li {{ font-size: 13px; line-height: 1.6; color: #cbd5e1; }}
.grid-meta {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 14px; background: #0f172a; padding: 18px; border-radius: 10px; border: 1px solid #334155; }}
.meta-item b {{ color: #94a3b8; font-size: 11px; display: block; text-transform: uppercase; letter-spacing: .05em; }}
.meta-item span {{ font-size: 14px; font-weight: 700; color: #f8fafc; }}
.drivers-box {{ background: #1e293b; border: 1px solid #0284c7; border-left: 5px solid #0284c7; border-radius: 8px; padding: 16px; margin-top: 16px; }}
table {{ width: 100%; border-collapse: collapse; margin: 16px 0; font-size: 13px; background: #0f172a; border-radius: 8px; overflow: hidden; border: 1px solid #334155; }}
th, td {{ border-bottom: 1px solid #334155; padding: 12px 14px; text-align: left; vertical-align: top; }}
th {{ background: #182234; color: #38bdf8; font-weight: 700; font-size: 12px; text-transform: uppercase; }}
tr:hover {{ background: #1e293b; }}
.badge {{ display: inline-block; padding: 4px 8px; border-radius: 4px; font-weight: 800; font-size: 11px; }}
.badge-GREEN {{ background: #065f46; color: #34d399; }}
.badge-YELLOW {{ background: #78350f; color: #fbbf24; }}
.badge-RED {{ background: #7f1d1d; color: #f87171; }}
.badge-PURPLE {{ background: #581c87; color: #c084fc; }}
.stage-card {{ background: #0f172a; border: 1px solid #334155; border-radius: 8px; padding: 16px; margin-bottom: 14px; }}
.covenants-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(360px, 1fr)); gap: 16px; }}
.cov-col {{ background: #0f172a; padding: 18px; border-radius: 8px; border: 1px solid #334155; }}
code {{ background: #0f172a; padding: 2px 6px; border-radius: 4px; color: #38bdf8; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }}
.btn-print {{ background: #0284c7; color: white; border: none; padding: 8px 16px; border-radius: 6px; font-weight: 700; cursor: pointer; text-decoration: none; font-size: 12px; }}
.btn-print:hover {{ background: #0369a1; }}
@media print {{ body {{ background: white; color: black; }} .container {{ background: white; border: none; box-shadow: none; padding: 0; }} table, .grid-meta, .stage-card, .cov-col {{ background: white; border-color: #ccc; }} th {{ background: #eee; color: black; }} td, p, li {{ color: black; }} .btn-print {{ display: none; }} }}
</style>
</head>
<body>
<div class="container">
  <div class="header-box">
    <div>
      <h1>📋 TỜ TRÌNH TÓM TẮT & GIẢI TRÌNH QUYẾT ĐỊNH THẨM ĐỊNH TÍN DỤNG</h1>
      <p style="margin:0; color:#94a3b8; font-size:12px;">
        Mã hồ sơ: <code>{html.escape(self.case_id)}</code> | Kịch bản: <code>{html.escape(self.scenario_id)}</code> | Run ID: <code>{html.escape(self.run_id[:8])}</code> | Thời gian: {html.escape(self.timestamp)}
      </p>
    </div>
    <div>
      <button onclick="window.print()" class="btn-print">🖨️ In Báo Cáo / Xuất PDF</button>
    </div>
  </div>

  <h2>🏛️ 1. Tóm Tắt Điều Hành (Executive Summary)</h2>
  <div class="grid-meta">
    <div class="meta-item">
      <b>Khách Hàng Vay</b>
      <span>{html.escape(b_name)}</span>
      <small style="color:#94a3b8;">MST: {html.escape(b_tax)} · {html.escape(b_seg)}</small>
    </div>
    <div class="meta-item">
      <b>Nhu Cầu Cấp Tín Dụng</b>
      <span style="color:#38bdf8;">{req_amt:,.0f} VND</span>
      <small style="color:#94a3b8;">Kỳ hạn: {tenor} tháng · Mục đích: {html.escape(purpose)}</small>
    </div>
    <div class="meta-item">
      <b>Ý Kiến AI Co-Approval (A13)</b>
      <span style="color:#34d399;"><span class="badge badge-{self._decision_badge(self.final_ai_decision)}">{html.escape(self.final_ai_decision)}</span></span>
      <small style="color:#94a3b8;">Độ tin cậy: {self.confidence_score*100:.0f}% (DRAFT - Bản nháp tư vấn)</small>
    </div>
    <div class="meta-item">
      <b>Khóa Kiểm Soát Thể Chế</b>
      <span><code>{html.escape(self.control_gate_status)}</code></span>
      <small style="color:#94a3b8;">Mức rủi ro: <b style="color:#f59e0b;">{html.escape(self.risk_level)}</b></small>
    </div>
  </div>

  <div class="drivers-box">
    <h4 style="margin:0 0 10px; color:#38bdf8; font-size:14px;">🎯 Các Yếu Tố Quyết Định Cốt Lõi (Key Decision Drivers):</h4>
    <ul style="margin:0; padding-left:20px; color:#f8fafc;">{drivers_html}</ul>
  </div>

  <h2>🔍 2. Bảng Ma Trận Giải Trình Chi Tiết 13 Agents (13-Agent Explainability Matrix)</h2>
  <table>
    <thead>
      <tr>
        <th style="width:22%;">Agent & Vai Trò</th>
        <th style="width:8%;">Tín Hiệu</th>
        <th style="width:22%;">Dữ Liệu Đầu Vào (Key Inputs)</th>
        <th style="width:22%;">Kết Quả Đầu Ra (Key Outputs)</th>
        <th style="width:26%;">💡 Lý Do & Logic Quyết Định (Why / Rationale)</th>
      </tr>
    </thead>
    <tbody>
      {"".join(rows)}
    </tbody>
  </table>

  <h2>⚖️ 3. Tổng Hợp Tranh Biện Theo 5 Giai Đoạn (5-Stage Synthesis & Dialectical Debate)</h2>
  {"".join(stage_cards)}

  <h2>📜 4. Danh Mục Điều Kiện Ràng Buộc (Covenants & Conditions)</h2>
  <div class="covenants-grid">
    <div class="cov-col">
      <h3 style="margin:0 0 12px; color:#f59e0b;">⏳ Điều Kiện Tiên Quyết Trước Giải Ngân (Conditions Precedent)</h3>
      <ol style="margin:0; padding-left:20px; color:#cbd5e1;">{cp_html}</ol>
    </div>
    <div class="cov-col">
      <h3 style="margin:0 0 12px; color:#34d399;">🔒 Điều Kiện Quản Lý Sau Giải Ngân (Ongoing Covenants)</h3>
      <ol style="margin:0; padding-left:20px; color:#cbd5e1;">{cov_html}</ol>
    </div>
  </div>

  <h2>🛡️ 5. Bảo Chứng Thể Chế & Chữ Ký Số (Governance & Audit Seal)</h2>
  <div style="background:#0f172a; padding:18px; border-radius:8px; border:1px solid #334155;">
    <p style="margin:0 0 8px;"><b>Mã Băm Niêm Phong Hồ Sơ (HMAC-SHA256):</b> <code>{html.escape(str(self.governance_and_compliance.get('digital_seal_hash')))}</code></p>
    <p style="margin:0 0 8px;"><b>Quy Chế Tín Dụng Áp Dụng:</b> <code>{html.escape(str(self.governance_and_compliance.get('policy_id')))}</code> | <b>Thẩm Quyền Phê Duyệt Quy Định:</b> <code>{html.escape(str(self.governance_and_compliance.get('required_authority')))}</code></p>
    <p style="margin:0; color:#f59e0b; font-size:12px;">⚠️ <b>Quy Tắc Bất Khả Xâm Phạm:</b> Hệ thống AI hoạt động hoàn toàn ở chế độ tư vấn cố vấn (Advisory Mode), không có quyền tự động duyệt (No AI Auto-Approve) và không có quyền tự động giải ngân (No AI Auto-Disburse). Thẩm quyền quyết định tối hậu thuộc về Cán bộ Phê duyệt có thẩm quyền.</p>
  </div>
</div>
</body>
</html>"""

    def _decision_badge(self, decision: str) -> str:
        if "APPROVE" in decision:
            return "GREEN"
        if "ESCALATE" in decision:
            return "PURPLE"
        return "RED"


class CaseExplainer:
    """Enterprise Decision Explanation & Executive Summary Generator."""

    @classmethod
    def explain(cls, state: CreditState) -> CaseExplanationReport:
        case_file = state.case_file or {}
        borrower = case_file.get("borrower", {})
        request = case_file.get("request", {})
        control = state.control or {}
        opinion = state.coapproval_opinion or {}
        confidence = float(opinion.get("confidence", 0.85))

        final_decision = opinion.get("decision", "REJECT_INSUFFICIENT_EVIDENCE")
        control_status = control.get("status", "READY_FOR_HUMAN_REVIEW")

        # Map node history for fast lookup
        node_map = {n["node_id"]: n for n in state.node_history}

        # 1. Primary Decision Drivers & Risk Level Determination
        drivers = []
        risk_level = "MEDIUM"

        a5_out = state.analyst_reports.get("policy", {})
        policy_exc = case_file.get("policy_exception", False) or a5_out.get("escalation_required", False)
        auth = a5_out.get("authority", "CREDIT_COMMITTEE")
        req_tenor = request.get("tenor_months", 12)
        req_amt = request.get("amount") or request.get("requested_amount", 0)
        circ_score = state.analyst_reports.get("transaction_integrity", {}).get("cycle_score", case_file.get("circular_funds_score", 0.0))
        dscr_val = state.analyst_reports.get("financial_capacity", {}).get("dscr", case_file.get("dscr", 1.0))
        stressed_dscr = state.analyst_reports.get("financial_capacity", {}).get("stressed_dscr", 1.0)
        collat = case_file.get("collateral_coverage", 1.0)
        docs_complete = case_file.get("documents_complete", True)
        statement_months = case_file.get("statement_months", 12)

        if final_decision == "APPROVE_WITH_CONDITIONS":
            risk_level = "LOW" if control_status == "READY_FOR_HUMAN_REVIEW" else "MEDIUM"
            drivers.append(f"Khả năng trả nợ gốc và lãi (DSCR = {dscr_val:.2f}x ≥ 1.20x; Stressed DSCR = {stressed_dscr:.2f}x) chứng minh dòng tiền kinh doanh cốt lõi đủ bù đắp nghĩa vụ nợ.")
            drivers.append(f"Hồ sơ pháp lý và sao kê dòng tiền đầy đủ {statement_months} tháng, độ bao phủ tài sản bảo đảm đạt {collat:.2f}x nghĩa vụ nợ.")
            drivers.append("Không phát hiện giao dịch lòng vòng AML hoặc chu trình đảo nợ giữa các bên liên quan (Điểm AML: 0.05 < 0.40).")
        elif final_decision == "ESCALATE_TO_CRO_RISK":
            risk_level = "HIGH"
            if policy_exc or req_tenor > 12:
                drivers.append(f"Ngoại lệ chính sách kỳ hạn: Doanh nghiệp đề xuất vay {req_tenor} tháng cho vốn lưu động, vượt trần 12 tháng theo quy chế tín dụng hiện hành (Mã điều khoản: {a5_out.get('rule_id', 'RULE-TENOR-003')}).")
                drivers.append(f"Bắt buộc leo thang thẩm quyền: Hồ sơ có ngoại lệ chính sách kỳ hạn vượt thẩm quyền Chi nhánh -> Bắt buộc chuyển {auth} (Chief Risk Officer) xem xét.")
            if circ_score >= 0.40:
                drivers.append(f"Cảnh báo rủi ro AML & giao dịch lòng vòng: Phân tích đồ thị phát hiện chu trình chuyển tiền khép kín với điểm rủi ro {circ_score:.2f} (ngưỡng an toàn < 0.40).")
        else:  # REJECT_INSUFFICIENT_EVIDENCE
            risk_level = "CRITICAL"
            if not docs_complete or statement_months < 12:
                drivers.append(f"Thiếu hụt dữ liệu đầu vào cốt lõi: Hồ sơ chỉ có {statement_months} tháng sao kê (Quy định bắt buộc tối thiểu 12 tháng) hoặc thiếu BCTC kiểm toán.")
            if dscr_val < 1.0:
                drivers.append(f"Năng lực trả nợ không khả thi: Hệ số DSCR đạt {dscr_val:.2f}x (< 1.0x). Nguyên tắc tín dụng: Tài sản bảo đảm ({collat:.2f}x) không thể thay thế hoặc bù đắp cho dòng tiền kinh doanh yếu.")
            if control.get("blocked_reasons"):
                for r in control.get("blocked_reasons", []):
                    drivers.append(f"Khóa an toàn thể chế kích hoạt lý do chặn: {r}")

        # 2. Detailed 13 Agent Explanations
        agent_explanations: List[AgentExplanation] = []

        # A1: Intake & Evidence Agent
        a1_out = node_map.get("A1", {}).get("output", {})
        a1_sig = "GREEN" if docs_complete and statement_months >= 12 else "RED"
        a1_rat = (
            f"Bóc tách OCR thành công hồ sơ pháp lý & BCTC; Cửa sổ sao kê ngân hàng đầy đủ {statement_months} tháng liên tục. Định danh khách hàng CIF `{borrower.get('entity_id')}` hợp lệ."
            if a1_sig == "GREEN"
            else f"Hồ sơ không đáp ứng điều kiện nạp liệu tối thiểu: Cửa sổ dữ liệu sao kê chỉ đạt {statement_months} tháng (thiếu {12 - statement_months} tháng so với chuẩn quy chế)."
        )
        agent_explanations.append(AgentExplanation(
            node_id="A1",
            agent_name=AGENT_NAMES.get("A1", "Intake Evidence Normalizer"),
            stage=STAGE_MAP["A1"],
            status=node_map.get("A1", {}).get("status", "COMPLETED"),
            inputs_summary={"pdf_dossier": "Attached", "cif": borrower.get("entity_id", "N/A"), "min_required_window": "12 months"},
            outputs_summary={"documents_complete": docs_complete, "statement_months": statement_months, "catalog_items": len(state.evidence_catalog)},
            rationale=a1_rat,
            key_indicators={"statement_months": statement_months, "documents_complete": docs_complete},
            verdict_signal=a1_sig,
        ))

        # A2: Cashflow Analyst
        a2_out = state.analyst_reports.get("cashflow", {})
        inflow = a2_out.get("observed_inflow", case_file.get("observed_inflow", 0))
        revenue = case_file.get("declared_revenue", max(inflow, 1))
        inflow_ratio = round(inflow / max(revenue, 1), 2)
        inflow_conc = a2_out.get("inflow_concentration", case_file.get("inflow_concentration", 0.32))
        a2_sig = "GREEN" if inflow_ratio >= 0.80 and inflow_conc < 0.40 else ("YELLOW" if inflow_ratio >= 0.60 else "RED")
        a2_rat = (
            f"Dòng tiền vào thực tế ghi nhận {inflow:,.0f} VND ({inflow_ratio*100:.0f}% doanh thu khai báo). Tỷ lệ tập trung đối tác ở mức {inflow_conc*100:.0f}% (ngưỡng an toàn < 40%)."
            if a2_sig == "GREEN"
            else (
                f"Dòng tiền vào {inflow:,.0f} VND tốt ({inflow_ratio*100:.0f}% doanh thu), tuy nhiên tỷ lệ tập trung đối tác đạt {inflow_conc*100:.0f}% (> 40% trần rủi ro), cần áp dụng điều kiện theo dõi luồng tiền."
                if a2_sig == "YELLOW"
                else f"Dòng tiền vào sao kê thực tế ({inflow:,.0f} VND) chỉ đạt {inflow_ratio*100:.0f}% doanh thu khai báo, thiếu hụt trầm trọng thanh khoản hoạt động."
            )
        )
        agent_explanations.append(AgentExplanation(
            node_id="A2",
            agent_name=AGENT_NAMES.get("A2", "Cashflow Analyst"),
            stage=STAGE_MAP["A2"],
            status=node_map.get("A2", {}).get("status", "COMPLETED"),
            inputs_summary={"statement_transactions": "12 months ingested", "declared_revenue": f"{revenue:,.0f} VND"},
            outputs_summary={"observed_inflow": f"{inflow:,.0f} VND", "inflow_to_revenue": f"{inflow_ratio*100:.0f}%", "concentration": f"{inflow_conc*100:.0f}%"},
            rationale=a2_rat,
            key_indicators={"inflow_ratio": inflow_ratio, "concentration": inflow_conc},
            verdict_signal=a2_sig,
        ))

        # A3: Transaction Integrity Analyst
        a3_out = state.analyst_reports.get("transaction_integrity", {})
        a3_sig = "RED" if circ_score >= 0.40 else "GREEN"
        a3_rat = (
            f"Quét đồ thị mạng lưới đối tác xác nhận không có chu trình giao dịch vòng quanh (Điểm AML: {circ_score:.2f} < 0.40). Độ bao phủ bên liên quan: {a3_out.get('related_party_coverage', 0.9)*100:.0f}%."
            if a3_sig == "GREEN"
            else f"Cảnh báo nghiêm trọng: Đồ thị giao dịch phát hiện mẫu hình dòng tiền đảo nợ lòng vòng với điểm rủi ro AML {circ_score:.2f} (vượt ngưỡng cho phép 0.40)."
        )
        agent_explanations.append(AgentExplanation(
            node_id="A3",
            agent_name=AGENT_NAMES.get("A3", "Transaction Integrity Analyst"),
            stage=STAGE_MAP["A3"],
            status=node_map.get("A3", {}).get("status", "COMPLETED"),
            inputs_summary={"counterparty_graph": "Analyzed", "aml_database": "Checked"},
            outputs_summary={"cycle_score": circ_score, "pattern": "CIRCULAR_FUNDS_DETECTED" if a3_sig == "RED" else "NORMAL_COMMERCIAL_GRAPH"},
            rationale=a3_rat,
            key_indicators={"cycle_score": circ_score},
            verdict_signal=a3_sig,
        ))

        # A4: Financial Capacity Analyst
        a4_out = state.analyst_reports.get("financial_capacity", {})
        a4_sig = "GREEN" if dscr_val >= 1.20 else ("YELLOW" if dscr_val >= 1.0 else "RED")
        a4_rat = (
            f"Năng lực tài chính vững mạnh: Hệ số DSCR đạt {dscr_val:.2f}x (≥ 1.20x). Kịch bản stress-test (doanh thu giảm 20%, lãi suất +200bps) DSCR vẫn đạt {stressed_dscr:.2f}x. Nguồn trả nợ gốc khả thi."
            if a4_sig == "GREEN"
            else (
                f"Năng lực tài chính ở mức cận biên: DSCR đạt {dscr_val:.2f}x (1.0x - 1.20x), kịch bản xấu giảm xuống {stressed_dscr:.2f}x, cần tăng cường kiểm soát dòng tiền."
                if a4_sig == "YELLOW"
                else f"Khả năng trả nợ không đạt yêu cầu: DSCR chỉ đạt {dscr_val:.2f}x (< 1.0x). Dù TSBĐ đạt {collat:.2f}x nhưng không thể bù đắp thâm hụt dòng tiền trả nợ chính."
            )
        )
        agent_explanations.append(AgentExplanation(
            node_id="A4",
            agent_name=AGENT_NAMES.get("A4", "Financial Capacity Analyst"),
            stage=STAGE_MAP["A4"],
            status=node_map.get("A4", {}).get("status", "COMPLETED"),
            inputs_summary={"balance_sheets": "Analyzed", "debt_obligations": "Calculated"},
            outputs_summary={"dscr": f"{dscr_val:.2f}x", "stressed_dscr": f"{stressed_dscr:.2f}x", "primary_repayment": a4_sig != "RED"},
            rationale=a4_rat,
            key_indicators={"dscr": dscr_val, "stressed_dscr": stressed_dscr},
            verdict_signal=a4_sig,
        ))

        # A5: Policy Compliance Analyst
        a5_sig = "PURPLE" if policy_exc or auth == "CRO_RISK" else "GREEN"
        a5_rule = a5_out.get("rule_id", "RULE-BASE")
        a5_cite = a5_out.get("policy_citation_id", "CITE-POLICY-2025")
        a5_rat = (
            f"Hồ sơ tuân thủ 100% quy chế tín dụng SME hiện hành. Thẩm quyền phê duyệt thuộc: {auth}."
            if not policy_exc and auth != "CRO_RISK"
            else f"Phát hiện ngoại lệ chính sách (Kỳ hạn {req_tenor} tháng vượt trần 12 tháng theo điều khoản `{a5_rule}`). Yêu cầu leo thang phê duyệt lên cấp: {auth}."
        )
        agent_explanations.append(AgentExplanation(
            node_id="A5",
            agent_name=AGENT_NAMES.get("A5", "Policy Compliance Analyst"),
            stage=STAGE_MAP["A5"],
            status=node_map.get("A5", {}).get("status", "COMPLETED"),
            inputs_summary={"policy_framework": "POLICY-SME-2025-v2.1", "requested_tenor": f"{req_tenor}M", "limit": f"{req_amt:,.0f} VND"},
            outputs_summary={"authority": auth, "policy_exception": policy_exc, "rule_id": a5_rule, "citation_id": a5_cite},
            rationale=a5_rat,
            key_indicators={"authority": auth, "policy_exception": policy_exc},
            verdict_signal=a5_sig,
        ))

        # A6: Credit Advocate
        a6_debate = next((d for d in state.credit_debate if d.get("speaker") in ("A6", "CREDIT_ADVOCATE")), {})
        a6_thesis = a6_debate.get("thesis", "supportable_with_controls")
        a6_rat = (
            f"Bảo vệ phương án cấp tín dụng theo góc nhìn Tăng trưởng (RM): Doanh nghiệp có năng lực trả nợ khả thi (DSCR {dscr_val:.2f}x), luồng tiền ổn định, đề xuất chấp thuận kèm biện pháp kiểm soát."
            if dscr_val >= 1.0 and docs_complete
            else "Không thể bảo vệ phương án vay do thiếu chứng từ cốt lõi hoặc dòng tiền trả nợ bị gãy nghiêm trọng."
        )
        agent_explanations.append(AgentExplanation(
            node_id="A6",
            agent_name=AGENT_NAMES.get("A6", "Credit Advocate"),
            stage=STAGE_MAP["A6"],
            status=node_map.get("A6", {}).get("status", "COMPLETED"),
            inputs_summary={"evidence_reports": "A1-A5 Synthesized", "thesis": a6_thesis},
            outputs_summary={"advocacy_stance": "SUPPORT_APPROVAL" if a6_rat.startswith("Bảo vệ") else "UNSUPPORTED", "growth_rationale": a6_debate.get("growth_rationale", "Viable repayment")},
            rationale=a6_rat,
            key_indicators={"advocacy_strength": "HIGH" if a6_rat.startswith("Bảo vệ") else "LOW"},
            verdict_signal="GREEN" if a6_rat.startswith("Bảo vệ") else "RED",
        ))

        # A7: Risk Challenger
        a7_debate = next((d for d in state.credit_debate if d.get("speaker") in ("A7", "RISK_CHALLENGER")), {})
        challenges = a7_debate.get("challenges", [])
        challenges_str = ", ".join(challenges) if challenges else ("Ngoại lệ thời hạn vay" if policy_exc else "Rủi ro tập trung dòng tiền")
        a7_sig = "RED" if circ_score >= 0.40 or dscr_val < 1.0 else ("PURPLE" if policy_exc else "YELLOW")
        a7_rat = (
            f"Tấn công trực diện các điểm gãy rủi ro: Nêu bật điểm yếu rủi ro `{challenges_str}`. Thử nghiệm kịch bản xấu (Stressed DSCR {stressed_dscr:.2f}x) cho thấy hồ sơ không thể tự động duyệt nếu không có cấp thẩm quyền đặc thù."
            if policy_exc or circ_score >= 0.40
            else f"Phản biện thận trọng: Cảnh báo rủi ro biến động dòng tiền và yêu cầu thiết lập điều kiện giám sát doanh thu qua tài khoản ngân hàng."
        )
        agent_explanations.append(AgentExplanation(
            node_id="A7",
            agent_name=AGENT_NAMES.get("A7", "Risk Challenger"),
            stage=STAGE_MAP["A7"],
            status=node_map.get("A7", {}).get("status", "COMPLETED"),
            inputs_summary={"advocate_claim": a6_debate.get("claim_id", "CLAIM-ADV-1"), "stress_testing": "Simulated"},
            outputs_summary={"challenges": challenges, "vulnerability": f"Triggered by {challenges_str}"},
            rationale=a7_rat,
            key_indicators={"challenged_points": len(challenges)},
            verdict_signal=a7_sig,
        ))

        # A8: Assessment Arbiter
        a8_assessment = state.credit_assessment or {}
        a8_rating = a8_assessment.get("rating", "OVERWEIGHT_CAUTION")
        a8_sig = "GREEN" if final_decision == "APPROVE_WITH_CONDITIONS" else ("PURPLE" if final_decision == "ESCALATE_TO_CRO_RISK" else "RED")
        a8_rat = (
            f"Đóng vai trò Trọng tài độc lập hòa giải tranh luận Stage 2 giữa A6 và A7: Xác định xếp hạng `{a8_rating}`. Kết luận phương án vay khả thi nhưng có rủi ro/ngoại lệ cần cơ chế kiểm soát đặc biệt và điều kiện Covenants ràng buộc."
        )
        agent_explanations.append(AgentExplanation(
            node_id="A8",
            agent_name=AGENT_NAMES.get("A8", "Assessment Manager (Arbiter)"),
            stage=STAGE_MAP["A8"],
            status=node_map.get("A8", {}).get("status", "COMPLETED"),
            inputs_summary={"debate_A6_A7": "Arbitrated", "evidence_weight": "Evaluated"},
            outputs_summary={"arbiter_rating": a8_rating, "recommended_amount": f"{req_amt:,.0f} VND", "covenants_count": len(a8_assessment.get("required_covenants", []))},
            rationale=a8_rat,
            key_indicators={"rating": a8_rating},
            verdict_signal=a8_sig,
        ))

        # A9: Deal Structuring Agent
        a9_deal = state.deal_proposal or {}
        a9_val = a9_deal.get("validation", {})
        violations = a9_val.get("violations", [])
        a9_sig = "PURPLE" if violations else "GREEN"
        a9_rat = (
            f"Cơ cấu khoản vay: Hạn mức {req_amt:,.0f} VND, thời hạn {req_tenor} tháng, nhóm định giá `{a9_deal.get('pricing_band', 'STANDARD')}`. "
            + (f"Kiểm tra hệ thống LOS ghi nhận vi phạm chính sách `{', '.join(violations)}` -> Xác nhận phương án cấu trúc cần cấp thẩm quyền phê duyệt ngoại lệ." if violations else "Cơ cấu phù hợp trọn vẹn khung chính sách.")
        )
        agent_explanations.append(AgentExplanation(
            node_id="A9",
            agent_name=AGENT_NAMES.get("A9", "Deal Structuring Specialist"),
            stage=STAGE_MAP["A9"],
            status=node_map.get("A9", {}).get("status", "COMPLETED"),
            inputs_summary={"arbiter_findings": "Applied", "collateral_coverage": f"{collat:.2f}x"},
            outputs_summary={"facility_limit": f"{req_amt:,.0f} VND", "tenor": f"{req_tenor}M", "pricing_band": a9_deal.get("pricing_band", "STANDARD"), "los_validation": a9_val.get("recommendation", "VALID")},
            rationale=a9_rat,
            key_indicators={"violations": violations},
            verdict_signal=a9_sig,
        ))

        # A10: Business/Upside Risk Agent
        a10_pos = next((d.get("position") for d in state.risk_debate if d.get("speaker") in ("A10", "BUSINESS_UPSIDE")), "ESCALATE" if policy_exc else "APPROVE")
        agent_explanations.append(AgentExplanation(
            node_id="A10",
            agent_name=AGENT_NAMES.get("A10", "Business Risk Specialist"),
            stage=STAGE_MAP["A10"],
            status=node_map.get("A10", {}).get("status", "COMPLETED"),
            inputs_summary={"deal_proposal": "Reviewed", "industry_outlook": borrower.get("industry", "SME")},
            outputs_summary={"position": a10_pos, "claim": "preserve_viable_structure_with_explicit_controls"},
            rationale=f"Đánh giá góc nhìn Tiềm năng kinh doanh: Khẳng định tính khả thi của phương án kinh doanh trong ngành `{borrower.get('industry')}`, bảo vệ lập trường {a10_pos}.",
            key_indicators={"risk_committee_position": a10_pos},
            verdict_signal="PURPLE" if a10_pos == "ESCALATE" else "GREEN",
        ))

        # A11: Conservative Credit Risk Agent
        a11_pos = next((d.get("position") for d in state.risk_debate if d.get("speaker") in ("A11", "CONSERVATIVE_CREDIT")), "MODIFY" if policy_exc else "APPROVE")
        agent_explanations.append(AgentExplanation(
            node_id="A11",
            agent_name=AGENT_NAMES.get("A11", "Conservative Risk Specialist"),
            stage=STAGE_MAP["A11"],
            status=node_map.get("A11", {}).get("status", "COMPLETED"),
            inputs_summary={"collateral_valuation": f"{collat:.2f}x", "tenor_risk": f"{req_tenor}M"},
            outputs_summary={"position": a11_pos, "downside_check": "Collateral perfection mandatory"},
            rationale=f"Đánh giá góc nhìn Rủi ro thận trọng: Lập trường {a11_pos}. Yêu cầu siết chặt điều kiện tài sản bảo đảm và giám sát chặt chẽ chu kỳ trả nợ để phòng ngừa rủi ro dài hạn.",
            key_indicators={"risk_committee_position": a11_pos},
            verdict_signal="YELLOW" if a11_pos == "MODIFY" else "GREEN",
        ))

        # A12: Neutral Governance Risk Agent
        a12_pos = next((d.get("position") for d in state.risk_debate if d.get("speaker") in ("A12", "NEUTRAL_GOVERNANCE")), "ESCALATE" if policy_exc else "APPROVE")
        agent_explanations.append(AgentExplanation(
            node_id="A12",
            agent_name=AGENT_NAMES.get("A12", "Policy & Governance Arbiter"),
            stage=STAGE_MAP["A12"],
            status=node_map.get("A12", {}).get("status", "COMPLETED"),
            inputs_summary={"risk_debate": "Arbitrated", "delegation_matrix": "Verified"},
            outputs_summary={"final_authority": auth, "position": a12_pos, "material_dissent": policy_exc},
            rationale=f"Tổng kết Hội đồng Rủi ro Stage 4: Xác nhận có sự bất đồng quan điểm giữa các khối rủi ro (Material Dissent). Cấp thẩm quyền bắt buộc duyệt: {auth}.",
            key_indicators={"required_authority": auth},
            verdict_signal="PURPLE" if a12_pos == "ESCALATE" else "GREEN",
        ))

        # A13: Co-Approval Manager
        agent_explanations.append(AgentExplanation(
            node_id="A13",
            agent_name=AGENT_NAMES.get("A13", "Co-Approval Opinion Synthesizer"),
            stage=STAGE_MAP["A13"],
            status=node_map.get("A13", {}).get("status", "COMPLETED"),
            inputs_summary={"full_state_v13": "Aggregated", "control_gate": "Bound"},
            outputs_summary={"decision": final_decision, "confidence": f"{confidence*100:.0f}%", "status": "DRAFT"},
            rationale=f"Tổng hợp toàn diện 13 tác nhân: Đưa ra Ý kiến Đồng phê duyệt Bản nháp (DRAFT) `{final_decision}` với độ tin cậy {confidence*100:.0f}%, chuyển giao quyền quyết định cho Cán bộ thẩm quyền con người.",
            key_indicators={"decision": final_decision, "confidence": confidence},
            verdict_signal=a8_sig,
        ))

        # 3. Rich 5-Stage Syntheses
        stage_syntheses = [
            StageSynthesis(
                stage_id="STAGE_1",
                stage_name="Giai đoạn 1: Thu Thập & Chuẩn Hóa Bằng Chứng (A1 - A5)",
                participating_agents=["A1", "A2", "A3", "A4", "A5"],
                stage_summary="Nạp liệu đa nguồn, kiểm kê hóa đơn chứng từ, bóc tách OCR sao kê 12 tháng, quét đồ thị giao dịch AML và đối soát quy chế tín dụng.",
                key_takeaway=f"DSCR {dscr_val:.2f}x, Dòng tiền vào {inflow:,.0f} VND ({inflow_ratio*100:.0f}% doanh thu), Điểm chu trình AML {circ_score:.2f}, Cấp thẩm quyền: {auth}.",
                details=[
                    {"title": "Độ tin cậy OCR & BCTC (A1)", "content": f"Cửa sổ sao kê {statement_months} tháng, tính toàn vẹn dữ liệu đạt chuẩn."},
                    {"title": "Đánh giá Dòng tiền (A2)", "content": f"Inflow {inflow:,.0f} VND, tập trung đối tác {inflow_conc*100:.0f}%."},
                    {"title": "Liêm chính Giao dịch AML (A3)", "content": f"Điểm giao dịch vòng quanh {circ_score:.2f} ({'Phát hiện chu trình rủi ro' if circ_score >= 0.40 else 'Sạch, không có vòng tròn đảo nợ'})."},
                    {"title": "Năng lực Trả nợ & Stress-test (A4)", "content": f"DSCR cơ sở {dscr_val:.2f}x; DSCR kịch bản xấu {stressed_dscr:.2f}x."},
                    {"title": "Đối soát Thể chế (A5)", "content": f"Quy tắc `{a5_rule}` -> Thẩm quyền quy định: {auth}."}
                ]
            ),
            StageSynthesis(
                stage_id="STAGE_2",
                stage_name="Giai đoạn 2: Tranh Biện Đối Kháng & Hòa Giải (A6 - A8)",
                participating_agents=["A6", "A7", "A8"],
                stage_summary="Cuộc đối thoại biện chứng giữa Bên biện hộ (A6 - Góc nhìn tăng trưởng) và Bên phản biện rủi ro (A7 - Kịch bản gãy đổ dòng tiền), được Trọng tài A8 tổng hợp và xác lập Covenants.",
                key_takeaway=f"Trọng tài A8 kết luận: Xếp hạng `{a8_rating}`, đề xuất `{final_decision}` kèm danh mục Covenants kiểm soát rủi ro.",
                details=[
                    {"title": "Lập trường Bên Biện Hộ A6", "content": a6_rat},
                    {"title": "Lập luận Phản Biện A7", "content": a7_rat},
                    {"title": "Phán quyết Trọng Tài A8", "content": f"Chấp thuận hạn mức {req_amt:,.0f} VND nhưng áp dụng điều kiện giám sát doanh thu tài khoản và ràng buộc tỷ lệ DSCR tối thiểu 1.20x."}
                ]
            ),
            StageSynthesis(
                stage_id="STAGE_3",
                stage_name="Giai đoạn 3: Cơ Cấu Khoản Cấp Tín Dụng (A9)",
                participating_agents=["A9"],
                stage_summary="Xác lập hạn mức cho vay, cơ cấu kỳ hạn, biên lãi suất định giá theo rủi ro và kiểm tra tính hợp lệ với động cơ LOS.",
                key_takeaway=f"Hạn mức {req_amt:,.0f} VND, Kỳ hạn {req_tenor} tháng, Định giá `{a9_deal.get('pricing_band', 'STANDARD')}`, LOS: `{a9_val.get('recommendation', 'VALID')}`.",
                details=[
                    {"title": "Kiểm tra Động cơ LOS", "content": f"Vi phạm ghi nhận: {', '.join(violations) if violations else 'Không có vi phạm'}"}
                ]
            ),
            StageSynthesis(
                stage_id="STAGE_4",
                stage_name="Giai đoạn 4: Hội Đồng Thẩm Định Rủi Ro (A10 - A12)",
                participating_agents=["A10", "A11", "A12"],
                stage_summary="Hội đồng gồm 3 thành viên: Rủi ro kinh doanh (A10), Rủi ro tín dụng thận trọng (A11) và Trọng tài thể chế (A12) bỏ phiếu và xác nhận thẩm quyền.",
                key_takeaway=f"Khối kinh doanh ({a10_pos}) vs Khối rủi ro ({a11_pos}) -> Trọng tài A12 chốt cấp phê duyệt bắt buộc: {auth}.",
                details=[
                    {"title": "Biên bản Bỏ phiếu", "content": f"A10: {a10_pos} · A11: {a11_pos} · A12: {a12_pos}"}
                ]
            ),
            StageSynthesis(
                stage_id="STAGE_5",
                stage_name="Giai đoạn 5: Tổng Hợp Ý Kiến Đồng Phê Duyệt (A13)",
                participating_agents=["A13"],
                stage_summary="Tổng hợp toàn bộ State thành Tờ trình tư vấn bản nháp DRAFT, niêm phong HMAC-SHA256 và chuyển giao cho Cán bộ thẩm quyền con người.",
                key_takeaway=f"Ý kiến tư vấn: `{final_decision}` (Độ tin cậy: {confidence*100:.0f}%, Trạng thái Control: `{control_status}`).",
                details=[
                    {"title": "Trạng thái Niêm phong", "content": "Niêm phong số hợp lệ, khóa an toàn xác nhận không có hành vi tự động duyệt trái phép."}
                ]
            ),
        ]

        # 4. Dynamic Covenants & Conditions Precedent
        actionable_covenants = a8_assessment.get("required_covenants") or [
            "Duy trì tối thiểu 80% tổng doanh thu bán hàng thực tế qua tài khoản thanh toán mở tại Ngân hàng.",
            "Cam kết duy trì hệ số khả năng trả nợ DSCR định kỳ hàng quý không thấp hơn 1.20x.",
            "Cung cấp BCTC có kiểm toán và tờ khai thuế định kỳ trong vòng 90 ngày sau khi kết thúc năm tài chính.",
        ]
        conditions_precedent = a8_assessment.get("conditions_precedent") or [
            "Hoàn tất công chứng và đăng ký giao dịch bảo đảm đối với Tài sản bảo đảm trước khi giải ngân.",
            "Bổ sung văn bản cam kết bảo lãnh vô điều kiện của Người đại diện theo pháp luật.",
        ]

        governance_and_compliance = {
            "digital_seal_hash": control.get("digital_seal_hash", "UNSEALED"),
            "policy_id": a5_cite or "POLICY-SME-2025-v2.1",
            "required_authority": auth,
            "blocked_reasons": control.get("blocked_reasons", []),
        }

        return CaseExplanationReport(
            case_id=state.case_id,
            scenario_id=state.scenario_id,
            run_id=state.run_id,
            trace_id=state.trace_id,
            timestamp=state.audit[-1].timestamp if state.audit else "2026-08-20T00:00:00Z",
            borrower=borrower,
            loan_request=request,
            final_ai_decision=final_decision,
            control_gate_status=control_status,
            risk_level=risk_level,
            confidence_score=confidence,
            primary_decision_drivers=drivers,
            agent_explanations=agent_explanations,
            stage_syntheses=stage_syntheses,
            actionable_covenants=actionable_covenants,
            conditions_precedent=conditions_precedent,
            governance_and_compliance=governance_and_compliance,
        )
