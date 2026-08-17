# 11. Sơ Đồ & Luồng Dữ Liệu Toàn Bộ Hành Trình (End-to-End Data Flow Architecture)

---

## 1. Tổng Quan Luồng Dữ Liệu Hành Trình (Data Flow Overview)

Luồng dữ liệu của **CreditAgent** trải qua 4 lớp tương tác chính:
1. **Backend Core Systems (Input Data Sources):** 6 hệ thống backend ngân hàng cung cấp dữ liệu qua 25 Tools.
2. **Shared State Engine (`CreditState` Pipeline):** Trạng thái tập trung lan truyền qua 13 AI Agents (5 Stages), được biến đổi bất biến (Immutable State Versioning) qua `StatePatch`.
3. **Control & Governance Engine (Deterministic Rules):** Khóa an toàn 0-LLM tự động kiểm tra vi phạm chính sách & rủi ro.
4. **Human Authority & Audit Persistence:** Lưu trữ 14 Checkpoints SHA-256 vào SQLite localDB và giao diện Ký số duyệt vay con người.

---

## 2. Sơ Đồ Luồng Dữ Liệu Tổng Thể (Mermaid Data Flow Diagram)

```mermaid
flowchart TB
    subgraph BACKENDS["🏦 1. Hệ Thống Backend & 25 Tools (Data Ingestion)"]
        direction TB
        B1["DMS / OCR Engine<br/><i>(BCTC, Sao kê, MST)</i>"]
        B2["Core Banking / CBS<br/><i>(CIF, Lịch sử tín dụng)</i>"]
        B3["Graph DB / Neo4j<br/><i>(Giao dịch vòng tròn)</i>"]
        B4["Financial Spreading<br/><i>(DSCR, BCTC Ratios)</i>"]
        B5["Policy BRE / RAG<br/><i>(Thể chế, Hạn mức)</i>"]
        B6["LOS / Pricing Engine<br/><i>(Cấu trúc khoản vay, Lãi suất)</i>"]
    end

    subgraph STATE0["📦 Shared State Init"]
        S_INIT[("CreditState v0<br/>case_id, run_id, scenario")]
    end

    subgraph STAGE1["🤖 Stage 1: Evidence Production Team"]
        A1["A1 Intake & Evidence"]
        A2["A2 Cashflow Analyst"]
        A3["A3 Transaction Integrity"]
        A4["A4 Financial Capacity"]
        A5["A5 Policy Compliance"]
        
        S_INIT -->|Intake Document Payload| A1
        A1 -->|CreditState v1| BARRIER_FANOUT{"Parallel Fan-out Barrier"}
        
        BARRIER_FANOUT -->|Read v1| A2
        BARRIER_FANOUT -->|Read v1| A3
        BARRIER_FANOUT -->|Read v1| A4

        B1 -->|extract_statements| A2
        B3 -->|detect_circular_funds| A3
        B4 -->|calculate_dscr| A4
        B2 -->|fetch_cif_profile| A1

        A2 -->|cashflow_analysis| BARRIER_JOIN{"Merge Barrier"}
        A3 -->|integrity_signals| BARRIER_JOIN
        A4 -->|financial_capacity| BARRIER_JOIN

        BARRIER_JOIN -->|CreditState v5| A5
        B5 -->|check_policy_rules| A5
    end

    subgraph STAGE2["⚔️ Stage 2: Credit Challenge Team"]
        A6["A6 Credit Advocate"]
        A7["A7 Risk Challenger"]
        A8["A8 Assessment Manager"]

        A5 -->|CreditState v6<br/>policy_results| A6
        A6 -->|Advocate Pos| A7
        A7 -->|Risk Counterpoints| A8
    end

    subgraph STAGE3["📐 Stage 3: Deal Structuring"]
        A9["A9 Deal Structuring"]
        A8 -->|Assessment Report| A9
        B6 -->|pricing_matrix| A9
    end

    subgraph STAGE4["⚖️ Stage 4: Risk Committee"]
        A10["A10 Business Risk"]
        A11["A11 Conservative Risk"]
        A12["A12 Neutral Risk"]

        A9 -->|State v10| A10
        A10 -->|State v11| A11
        A11 -->|State v12| A12
    end

    subgraph STAGE5["📋 Stage 5: Advisory Opinion & Control"]
        A13["A13 Co-Approval Manager"]
        CTRL["Deterministic Approval Control"]

        A12 -->|State v13| A13
        A13 -->|State v14: CoApprovalOpinion DRAFT| CTRL
    end

    subgraph PERSIST["🗄️ Persistence & Human Decision Panel"]
        DB[("SQLite credit_agent.db<br/>14 SHA-256 Checkpoints")]
        HUMAN["👨‍⚖️ Human Final Authority<br/><i>(Form Ký Số & Quality Report)</i>"]

        CTRL -->|Checkpoint Save| DB
        CTRL -->|Ready for Review| HUMAN
        HUMAN -->|Record Decision & Hash| DB
    end

    style BACKENDS fill:#0f172a,stroke:#38bdf8,color:#38bdf8
    style STAGE1 fill:#064e3b,stroke:#4ade80,color:#4ade80
    style STAGE2 fill:#312e81,stroke:#c084fc,color:#c084fc
    style STAGE3 fill:#0c4a6e,stroke:#38bdf8,color:#38bdf8
    style STAGE4 fill:#451a03,stroke:#fbbf24,color:#fbbf24
    style STAGE5 fill:#4c1d95,stroke:#c084fc,color:#c084fc
    style PERSIST fill:#1e293b,stroke:#f43f5e,color:#f43f5e
```

---

## 3. Bảng Ma Trận Luồng Dữ Liệu Giữa Các Agent (Agent Data Pipeline Matrix)

| Agent Node | Dữ liệu Đầu Vào (Input Payload) | Backend Tool Sử Dụng | Dữ liệu Đầu Ra (Output State Patch) | Trạng thái State Version |
| :--- | :--- | :--- | :--- | :--- |
| **A1 Intake** | Hồ sơ doanh nghiệp đầu vào, thông tin khoản vay | `fetch_borrower_profile`, `extract_tax_records` | Danh sách hồ sơ pháp lý, danh mục chứng từ | `State v1` |
| **A2 Cashflow** | Snapshot `CreditState v1` (Sao kê ngân hàng) | `extract_bank_statements`, `analyze_cashflow` | Báo cáo dòng tiền (`cashflow_analysis`), DSCR dòng tiền | `State v2` (Nhánh A2) |
| **A3 Integrity** | Snapshot `CreditState v1` (Nhật ký giao dịch) | `detect_circular_counterparties`, `analyze_transaction_graph` | Tỷ lệ rủi ro vòng tròn (`circular_funds_score`), danh sách đối tác ảo | `State v3` (Nhánh A3) |
| **A4 Capacity** | Snapshot `CreditState v1` (BCTC 3 năm) | `extract_financial_statements`, `calculate_dscr` | Chỉ số DSCR, khả năng trả nợ, đòn bẩy tài chính | `State v4` (Nhánh A4) |
| **Barrier Join** | Gộp kết quả 3 nhánh A2, A3, A4 | Không sử dụng | Báo cáo tổng hợp `analyst_reports` | `State v5` |
| **A5 Policy** | `analyst_reports` từ v5 | `query_credit_policy_rules`, `check_regulatory_limits` | Kết quả kiểm tra thể chế (`policy_check_results`) | `State v6` |
| **A6 Advocate** | `analyst_reports` & `policy_results` | Không sử dụng | Lập luận ủng hộ vay (`advocate_position`) | `State v7` |
| **A7 Challenger** | `integrity_signals` (Circular Funds) & policy gaps | Không sử dụng | Lập luận phản biện rủi ro (`challenger_counterpoints`) | `State v8` |
| **A8 Assessment** | Tranh luận A6 vs A7 | Không sử dụng | Báo cáo thẩm định có trọng số (`assessment_summary`) | `State v9` |
| **A9 Structuring** | `assessment_summary` | `calculate_risk_adjusted_rate`, `generate_loan_structure` | Cấu trúc khoản vay, Tenor, Lãi suất, Tài sản đảm bảo | `State v10` |
| **A10 Business** | Cấu trúc khoản vay từ A9 | Không sử dụng | Đánh giá tiềm năng thị trường (`business_risk_opinion`) | `State v11` |
| **A11 Conservative**| Cấu trúc khoản vay từ A9 | Không sử dụng | Kịch bản stress-test rủi ro xấu nhất (`conservative_risk_opinion`) | `State v12` |
| **A12 Neutral** | Tổng hợp A10 & A11 | Không sử dụng | Quan điểm rủi ro trung lập (`neutral_risk_opinion`) | `State v13` |
| **A13 Co-Approval**| Tổng hợp toàn bộ 12 Agent trước | Không sử dụng | Dự thảo `CoApprovalOpinion` (`DRAFT`) | `State v14` |
| **Control Plane** | State v14 | Khóa an toàn Code xác định | Kết quả kiểm soát: `control` status & Hard blocks | Final Gate |

---

## 4. Chi Tiết Cấu Trúc Dữ Liệu `CreditState` Khi Truyền Qua Pipeline

```json
{
  "case_id": "CASE-APPROVE_CONDITIONS",
  "scenario_id": "approve_conditions",
  "run_id": "run-f47a9b1c",
  "state_version": 14,
  "financial_metrics": {
    "dscr": 1.35,
    "leverage_ratio": 2.1,
    "revenue_growth_pct": 14.5
  },
  "integrity_signals": {
    "circular_funds_score": 0.05,
    "suspicious_counterparties": []
  },
  "policy_check_results": {
    "sector_cap_ok": true,
    "policy_exceptions": []
  },
  "analyst_reports": {
    "A2_cashflow": "Dòng tiền sao kê ổn định 1.2 tỷ/tháng",
    "A3_integrity": "Không phát hiện dòng tiền vòng tròn",
    "A4_capacity": "DSCR 1.35 đạt yêu cầu tối thiểu 1.2"
  },
  "credit_debate": {
    "advocate_position": "Doanh nghiệp có dòng tiền thực và DSCR an toàn",
    "challenger_position": "Cần thắt chặt điều kiện bổ sung BCTC kiểm toán",
    "assessment_summary": "Đề xuất chấp thuận cho vay kèm điều kiện BCTC"
  },
  "proposed_facility": {
    "approved_amount": 5000000000,
    "approved_tenor_months": 12,
    "approved_interest_rate": 8.5
  },
  "draft_opinion": {
    "decision": "APPROVE_WITH_CONDITIONS",
    "rationale": "DSCR đạt 1.35, không rủi ro vòng tròn, đồng ý cho vay kèm điều kiện bổ sung BCTC"
  },
  "control": {
    "status": "READY_FOR_HUMAN_REVIEW",
    "hard_blocks": []
  }
}
```
