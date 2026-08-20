from __future__ import annotations

import html
import json
import logging
import urllib.error
import urllib.request
from typing import Any, Dict, Optional, Tuple

from .config import CONFIG
from .explainer import CaseExplainer, CaseExplanationReport
from .models import CreditState

logger = logging.getLogger(__name__)


class DeepSeekCreditSynthesizer:
    """Enterprise Credit Underwriting Narrative Synthesizer powered by DeepSeek LLM."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> None:
        self.api_key = api_key or CONFIG.DEEPSEEK_API_KEY
        self.base_url = (base_url or CONFIG.DEEPSEEK_BASE_URL).rstrip("/")
        self.model = model or CONFIG.DEEPSEEK_MODEL
        self.timeout = timeout or CONFIG.DEEPSEEK_TIMEOUT_SEC

    def is_configured(self) -> bool:
        return bool(self.api_key and self.api_key.strip())

    def build_prompt(self, state: CreditState) -> Tuple[str, str]:
        report: CaseExplanationReport = CaseExplainer.explain(state)
        rep_dict = report.to_dict()

        system_prompt = (
            "Bạn là Chuyên gia Thẩm định Tín dụng & Quản trị Rủi ro Cấp cao (Senior Credit Underwriter) "
            "tại một Ngân hàng Thương mại hàng đầu Việt Nam. Nhiệm vụ của bạn là nhận toàn bộ kết quả phân tích "
            "định lượng, tranh luận đối kháng và phán quyết thể chế của 13 AI Agents (State v1 -> v13) "
            "để tổng hợp thành một 'TỜ TRÌNH PHÂN TÍCH TÍN DỤNG CHUYÊN SÂU' (Credit Underwriting Narrative Memo) "
            "dành riêng cho Hội đồng Tín dụng và Cấp Phê duyệt có thẩm quyền.\n\n"
            "NGUYÊN TẮC BẮT BUỘC:\n"
            "1. Tuyệt đối trung thực với số liệu định lượng do 13 AI Agents cung cấp (Không tự bịa đặt số liệu hay ảo giác).\n"
            "2. Văn phong chuẩn mực ngân hàng, sắc bén, lập luận chặt chẽ, mạch lạc, có phân tích nguyên nhân - hệ quả.\n"
            "3. Thể hiện rõ nét cuộc đối thoại biện chứng giữa Bên bảo vệ tăng trưởng (RM) và Bên phản biện rủi ro (Risk).\n"
            "4. Định dạng đầu ra bằng Markdown chuyên nghiệp với các đề mục chuẩn sau:\n"
            "   # 📋 TỜ TRÌNH PHÂN TÍCH TÍN DỤNG CHUYÊN SÂU (CREDIT UNDERWRITING MEMO)\n"
            "   ## 1. TỔNG QUAN KHÁCH HÀNG & NHU CẦU CẤP TÍN DỤNG\n"
            "   ## 2. ĐÁNH GIÁ NĂNG LỰC TÀI CHÍNH & DÒNG TIỀN THỰC TẾ (CASHFLOW & DSCR)\n"
            "   ## 3. PHÂN TÍCH LIÊM CHÍNH GIAO DỊCH & RỦI RO AML (TRANSACTION GRAPH)\n"
            "   ## 4. TÓM LƯỢC TRANH BIỆN ĐỐI KHÁNG ĐA CHIỀU (DIALECTICAL DEBATE SYNTHESIS)\n"
            "   ## 5. ĐÁNH GIÁ HỘI ĐỒNG RỦI RO & PHÂN CẤP THẨM QUYỀN (RISK COMMITTEE PERSPECTIVES)\n"
            "   ## 6. Ý KIẾN TƯ VẤN ĐỒNG PHÊ DUYỆT & DANH MỤC COVENANTS RÀNG BUỘC\n"
        )

        user_prompt = (
            "Dưới đây là toàn bộ dữ liệu State có cấu trúc được trích xuất từ 13 Bounded AI Agents cho hồ sơ tín dụng:\n\n"
            + json.dumps(rep_dict, ensure_ascii=False, indent=2)
            + "\n\nHãy soạn thảo bản Tờ trình phân tích tín dụng chuyên sâu hoàn chỉnh, lập luận sắc bén và dễ đọc nhất cho Cán bộ Phê duyệt."
        )
        return system_prompt, user_prompt

    def generate_credit_memo(self, state: CreditState, prompt_override: Optional[str] = None) -> str:
        """Generates comprehensive credit narrative memo using DeepSeek API or deterministic fallback."""
        system_prompt, user_prompt = self.build_prompt(state)
        if prompt_override:
            user_prompt = prompt_override

        if not self.is_configured():
            logger.info("DeepSeek API Key not configured. Using high-grade deterministic synthesis memo.")
            return self._generate_fallback_memo(state, note="⚠️ (Chế độ mô phỏng nội bộ - Chưa nạp DeepSeek API Key vào config)")

        payload = {
            "model": self.model,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }

        try:
            url = f"{self.base_url}/chat/completions"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            content = data["choices"][0]["message"]["content"]

            from .logger import audit_log
            audit_log(
                event="DEEPSEEK_MEMO_GENERATED",
                component="DeepSeekCreditSynthesizer",
                trace_id=state.trace_id,
                case_id=state.case_id,
                details={
                    "model": self.model,
                    "prompt_length": len(system_prompt) + len(user_prompt),
                    "response_length": len(content),
                    "system_prompt": system_prompt,
                    "user_prompt": user_prompt,
                },
            )
            return content
        except Exception as e:
            logger.warning("DeepSeek API call failed: %s. Falling back to deterministic narrative.", e)
            from .logger import audit_log
            audit_log(
                event="DEEPSEEK_CALL_FAILED",
                component="DeepSeekCreditSynthesizer",
                trace_id=state.trace_id,
                case_id=state.case_id,
                level="WARNING",
                details={"error": str(e), "model": self.model},
            )
            return self._generate_fallback_memo(state, note=f"⚠️ (DeepSeek API Exception: {e} - Chuyển sang bản tổng hợp nội bộ)")

    def _generate_fallback_memo(self, state: CreditState, note: str = "") -> str:
        """Deterministic high-quality fallback generator when LLM API is unavailable."""
        report = CaseExplainer.explain(state)
        b = report.borrower
        req = report.loan_request
        b_name = b.get("name") or b.get("company_name", "N/A")
        b_tax = b.get("tax_code") or b.get("tax_id", "N/A")
        b_ind = b.get("industry", "N/A")
        b_seg = b.get("segment", "SME")
        req_amt = req.get("amount") or req.get("requested_amount", 0)
        tenor = req.get("tenor_months", 12)
        purpose = req.get("purpose", "working_capital")

        memo = []
        memo.append(f"# 📋 TỜ TRÌNH PHÂN TÍCH TÍN DỤNG CHUYÊN SÂU (CREDIT UNDERWRITING MEMO)")
        if note:
            memo.append(f"*{note}*\n")
        memo.append(f"**Mã Hồ sơ:** `{report.case_id}` | **Kịch bản:** `{report.scenario_id}` | **Run ID:** `{report.run_id[:8]}`")
        memo.append(f"**Thời gian lập tờ trình:** {report.timestamp}")
        memo.append(f"**Cán bộ phụ trách:** Khối Thẩm định Tín dụng & Quản trị Rủi ro Doanh nghiệp\n")
        memo.append("---")

        memo.append("## 1. TỔNG QUAN KHÁCH HÀNG & NHU CẦU CẤP TÍN DỤNG")
        memo.append(f"- **Tên khách hàng vay:** **{b_name}**")
        memo.append(f"- **Mã số thuế:** `{b_tax}` | **Phân khúc:** `{b_seg}` | **Ngành nghề kinh doanh cốt lõi:** `{b_ind}`")
        memo.append(f"- **Đề xuất cấp tín dụng:** Số tiền **{req_amt:,.0f} VND**, thời hạn **{tenor} tháng**, mục đích cho vay: `{purpose}`.")
        memo.append(f"- **Ý kiến AI Co-Approval (A13):** `{report.final_ai_decision}` (Độ tin cậy: **{report.confidence_score*100:.0f}%** · `DRAFT - Bản nháp tư vấn`).")
        memo.append(f"- **Khóa kiểm soát thể chế (Control Gate):** `{report.control_gate_status}` · Mức độ rủi ro: **{report.risk_level}**.\n")

        memo.append("## 2. ĐÁNH GIÁ NĂNG LỰC TÀI CHÍNH & DÒNG TIỀN THỰC TẾ (CASHFLOW & DSCR)")
        for a in report.agent_explanations:
            if a.node_id in ("A1", "A2", "A4"):
                memo.append(f"- **Đánh giá của {a.node_id} ({a.agent_name}):** {a.rationale}")
        memo.append("")

        memo.append("## 3. PHÂN TÍCH LIÊM CHÍNH GIAO DỊCH & RỦI RO AML (TRANSACTION GRAPH)")
        for a in report.agent_explanations:
            if a.node_id == "A3":
                memo.append(f"- **Đánh giá của A3 ({a.agent_name}):** {a.rationale}")
        memo.append("")

        memo.append("## 4. TÓM LƯỢC TRANH BIỆN ĐỐI KHÁNG ĐA CHIỀU (DIALECTICAL DEBATE SYNTHESIS)")
        for st in report.stage_syntheses:
            if st.stage_id == "STAGE_2":
                memo.append(f"- **Diễn biến vòng tranh biện Stage 2:** {st.stage_summary}")
                memo.append(f"- **Phán quyết của Trọng tài A8:** {st.key_takeaway}")
                if st.details:
                    for d in st.details:
                        memo.append(f"  - *{d.get('title')}:* {d.get('content')}")
        memo.append("")

        memo.append("## 5. ĐÁNH GIÁ HỘI ĐỒNG RỦI RO & PHÂN CẤP THẨM QUYỀN (RISK COMMITTEE PERSPECTIVES)")
        for st in report.stage_syntheses:
            if st.stage_id in ("STAGE_3", "STAGE_4"):
                memo.append(f"- **{st.stage_name}:** {st.stage_summary} -> *{st.key_takeaway}*")
        memo.append("")

        memo.append("## 6. Ý KIẾN TƯ VẤN ĐỒNG PHÊ DUYỆT & DANH MỤC COVENANTS RÀNG BUỘC")
        memo.append(f"- **Khuyến nghị cuối cùng của Hệ thống AI (A13):** `{report.final_ai_decision}`")
        if report.conditions_precedent:
            memo.append("### Điều kiện Tiên quyết trước Giải ngân (Conditions Precedent):")
            for i, cp in enumerate(report.conditions_precedent, 1):
                memo.append(f"{i}. {cp}")
        if report.actionable_covenants:
            memo.append("### Điều kiện Quản lý Sau Giải ngân (Ongoing Covenants):")
            for i, cov in enumerate(report.actionable_covenants, 1):
                memo.append(f"{i}. {cov}")
        memo.append("")
        memo.append("---")
        memo.append(f"**Mã Băm Niêm Phong Số (HMAC-SHA256):** `{report.governance_and_compliance.get('digital_seal_hash')}`")
        memo.append(f"**Thẩm quyền phê duyệt quy định:** `{report.governance_and_compliance.get('required_authority')}`")
        return "\n".join(memo)

    def generate_credit_memo_html(self, state: CreditState) -> str:
        """Generates a polished HTML document from the Markdown memo."""
        markdown_memo = self.generate_credit_memo(state)
        report = CaseExplainer.explain(state)

        return f"""<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Tờ Trình Phân Tích Tín Dụng AI - {html.escape(report.case_id)}</title>
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background: #0b1120; color: #f1f5f9; margin: 0; padding: 28px 16px; }}
.container {{ max-width: 1080px; margin: 0 auto; background: #1e293b; border-radius: 14px; border: 1px solid #334155; padding: 36px; box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.7); }}
.action-bar {{ display:flex; justify-content:space-between; align-items:center; border-bottom: 2px solid #334155; padding-bottom: 16px; margin-bottom: 24px; }}
.llm-badge {{ background: #0284c7; color: white; padding: 4px 10px; border-radius: 999px; font-size: 11px; font-weight: 800; }}
.btn-print {{ background: #0284c7; color: white; border: none; padding: 8px 16px; border-radius: 6px; font-weight: 700; cursor: pointer; font-size: 12px; }}
.btn-print:hover {{ background: #0369a1; }}
#memo-content h1 {{ color: #38bdf8; font-size: 22px; margin-top: 0; }}
#memo-content h2 {{ color: #93c5fd; font-size: 16px; border-bottom: 1px solid #334155; padding-bottom: 6px; margin-top: 24px; }}
#memo-content h3 {{ color: #cbd5e1; font-size: 14px; margin-top: 16px; }}
#memo-content p, #memo-content li {{ font-size: 13px; line-height: 1.65; color: #cbd5e1; }}
#memo-content code {{ background: #0f172a; padding: 2px 6px; border-radius: 4px; color: #38bdf8; font-family: monospace; }}
#memo-content blockquote {{ border-left: 4px solid #38bdf8; padding-left: 14px; margin-left: 0; color: #94a3b8; }}
@media print {{ body {{ background: white; color: black; }} .container {{ background: white; border: none; box-shadow: none; padding: 0; }} #memo-content h1, #memo-content h2 {{ color: black; }} .btn-print, .llm-badge {{ display: none; }} }}
</style>
</head>
<body>
<div class="container">
  <div class="action-bar">
    <div>
      <span class="llm-badge">🤖 DEEPSEEK LLM SYNTHESIS</span>
      <span style="font-size:12px; color:#94a3b8; margin-left:10px;">Model: <code>{html.escape(self.model)}</code></span>
    </div>
    <div>
      <button onclick="window.print()" class="btn-print">🖨️ In Tờ Trình / Xuất PDF</button>
    </div>
  </div>
  <div id="memo-content"></div>
</div>
<script>
  const rawMarkdown = {json.dumps(markdown_memo)};
  document.getElementById('memo-content').innerHTML = marked.parse(rawMarkdown);
</script>
</body>
</html>"""
