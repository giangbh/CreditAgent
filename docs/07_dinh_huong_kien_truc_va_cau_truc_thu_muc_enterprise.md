# 07. Định Hướng Kiến Trúc & Cấu Trúc Thư Mục Chuẩn Hóa Enterprise

---

## 1. Mục Đích & Phạm Vi

Tài liệu này quy định **Cấu trúc Thư mục Chuẩn hóa Enterprise** cho sản phẩm **CreditAgent (Luồng Thẩm Định Tín Dụng Đa Tác Nhân Có Kiểm Soát)**. Cấu trúc này được thiết kế theo nguyên lý **Clean Architecture / Hexagonal Architecture**, giúp hệ thống:
- Phân tách rõ ràng giữa **Nghiệp vụ Tín dụng (Domain Logic)**, **Tác nhân AI (Agents)**, **Công cụ Tích hợp (Tools)** và **Bộ quy tắc Kiểm soát Rủi ro (Control Gate)**.
- Dễ dàng mở rộng cho nhiều nhóm lập trình viên (Multi-team) cùng phát triển mà không bị xung đột mã nguồn.
- Sẵn sàng đấu nối với các hệ thống thật của Ngân hàng (Core Banking, CIC, hệ thống Khai thác OCR chứng từ, LOS).

---

## 2. Nguyên Tắc Thiết Kế (Design Principles)

1. **Phân tách Trách nhiệm (Separation of Concerns)**: Mỗi thư mục và mô-đun chỉ đảm nhận một nhóm nhiệm vụ duy nhất.
2. **Độc lập Hạ tầng (Infrastructure Independence)**: Core domain và quy tắc thẩm định không phụ thuộc trực tiếp vào khung điều phối (Temporal), cơ sở dữ liệu (SQLite/Postgres) hay nhà cung cấp LLM (OpenAI/vLLM/Gemini).
3. **Phân cấp An toàn (Strict Governance Isolation)**: Tầng kiểm soát an toàn (`governance/`) hoàn toàn độc lập với AI LLM, đảm bảo AI không bao giờ có thể tự vượt quyền phê duyệt hay tự giải ngân.

---

## 3. Cấu Trúc Thư Mục Enterprise Tổng Thể

```
CreditAgent/
├── config/                        # ⚙️ Cấu hình môi trường & Policy Versioning
│   ├── outcome_policy.v2.json     # Policy phân loại kết quả (Versioned)
│   ├── risk_rules.json            # Quy tắc hạn mức & rủi ro ngân hàng
│   └── settings.yaml              # Cấu hình Temporal, Database, LLM API Keys
│
├── src/
│   └── credit_agent/              # 📦 Package chính của sản phẩm
│       ├── __init__.py
│       ├── __main__.py
│       │
│       ├── domain/                # 1️⃣ TẦNG NGUYÊN BẢN NGHIỆP VỤ (Pure Domain & Entities)
│       │   ├── models/            # State, Opinion, CreditCase, AuditEvent
│       │   │   ├── credit_state.py
│       │   │   ├── opinion.py
│       │   │   └── human_decision.py
│       │   ├── exceptions.py      # Domain Exceptions (NarrativeTooShort, HardBlockError)
│       │   └── value_objects.py   # DecisionOutcome, IntegritySeal, RiskPath
│       │
│       ├── agents/                # 2️⃣ TẦNG 13 TÁC NHÂN LÔ-GÍCH (Modular Agents)
│       │   ├── base.py            # AgentBase class & Prompt Engine
│       │   ├── registry.py        # Dynamic Agent Registry & Lookup
│       │   ├── prompts/           # Quản lý Prompt templates (.jinja2 / .md)
│       │   │   ├── a1_intake.md
│       │   │   ├── a6_advocate.md
│       │   │   └── a7_challenger.md
│       │   ├── stage1_evidence/   # Stage 1: Nạp liệu & Phân tích bằng chứng
│       │   │   ├── a1_intake.py
│       │   │   ├── a2_cashflow.py
│       │   │   ├── a3_integrity.py
│       │   │   ├── a4_capacity.py
│       │   │   └── a5_policy.py
│       │   ├── stage2_challenge/  # Stage 2: Phản biện tín dụng
│       │   │   ├── a6_advocate.py
│       │   │   ├── a7_challenger.py
│       │   │   └── a8_manager.py
│       │   ├── stage3_structuring/# Stage 3: Cấu trúc khoản vay
│       │   │   └── a9_structuring.py
│       │   ├── stage4_risk/       # Stage 4: Hội đồng rủi ro
│       │   │   ├── a10_business.py
│       │   │   ├── a11_conservative.py
│       │   │   └── a12_neutral.py
│       │   └── stage5_opinion/    # Stage 5: Khuyến nghị tổng hợp
│       │       └── a13_coapproval.py
│       │
│       ├── tools/                 # 3️⃣ TẦNG CÔNG CỤ & TÍCH HỢP HỆ THỐNG (Tool Gateway)
│       │   ├── gateway.py         # Tool Gateway phân quyền theo Agent ID
│       │   ├── base.py            # BaseTool definition & validation
│       │   ├── simulated/         # Tool giả lập cho chạy Demo / Test
│       │   │   ├── intake_tools.py
│       │   │   ├── financial_tools.py
│       │   │   ├── integrity_tools.py
│       │   │   └── structuring_tools.py
│       │   └── adapters/          # Connector thực tế tới Core/API Ngân hàng
│       │       ├── cic_adapter.py             # Tra cứu Trung tâm Thông tin Tín dụng (CIC)
│       │       ├── core_banking_adapter.py    # Tra cứu Sao kê / Tài khoản từ Core Bank
│       │       ├── idp_ocr_adapter.py         # Trích xuất Báo cáo tài chính via IDP/OCR
│       │       └── collateral_adapter.py      # Định giá & Tra cứu TSBĐ
│       │
│       ├── governance/            # 4️⃣ TẦNG KIỂM SOÁT VÀ QUYỀN PHÊ DUYỆT (Control Gate)
│       │   ├── control_gate.py    # Thẩm định Độc lập & Hard-block checker
│       │   ├── integrity.py       # Mã băm Chữ ký số HMAC-SHA256 & Audit Chain
│       │   ├── authority.py       # Phân cấp Thẩm quyền Phê duyệt (CRO/Branch Director)
│       │   └── quality_analytics.py # Báo cáo chỉ số Chất lượng Cán bộ (Quality Index)
│       │
│       ├── orchestration/         # 5️⃣ TẦNG ĐIỀU PHỐI WORKFLOW (Temporal Engine)
│       │   ├── workflows/         # Temporal Workflow Defs
│       │   │   └── credit_workflow.py
│       │   ├── activities/        # Temporal Activities (Execute Agent/Tool)
│       │   │   └── agent_activities.py
│       │   ├── worker.py          # Temporal Worker Runner
│       │   └── engine.py          # Workflow Engine Switcher (Cluster vs Local)
│       │
│       └── infrastructure/        # 6️⃣ TẦNG HẠ TẦNG KỸ THUẬT (DB, API Server, LLM)
│           ├── db/                # Repository Pattern (SQLite / PostgreSQL)
│           │   ├── base.py
│           │   ├── sqlite_repo.py
│           │   └── postgres_repo.py
│           ├── llm/               # Adapter kết nối LLM (OpenAI / vLLM / Azure OpenAI)
│           │   ├── client.py
│           │   └── parsers.py     # Output Parser (JSON Repair / Schema Validation)
│           └── api/               # REST API Web Server
│               ├── server.py      # Server HTTP (FastAPI / ThreadingServer)
│               └── routes/        # Router endpoints (/scenarios, /human-decision, /analytics)
│
├── webui/                         # 7️⃣ GIAO DIỆN WEB PHÊ DUYỆT (Frontend Dashboard)
│   ├── src/
│   │   ├── components/            # WorkflowCanvas, HumanDecisionForm, QualityAnalytics
│   │   ├── i18n/                  # Dictionary dịch thuật (vi.json, en.json)
│   │   └── static/index.html
│
├── tests/                         # 8️⃣ BỘ KIỂM THỬ ĐẦY ĐỦ (Automated Tests)
│   ├── unit/                      # Test từng Agent, Control Gate, Seal
│   │   ├── test_control_gate.py
│   │   ├── test_integrity_seal.py
│   │   └── test_agents.py
│   ├── integration/               # Test luồng Temporal Workflow & DB
│   │   ├── test_temporal_workflow.py
│   │   └── test_repository.py
│   └── acceptance/                # Test 20 Bộ Tiêu chuẩn Nghiệm thu (AC1 - AC20)
│       └── test_acceptance_criteria.py
│
├── docs/                          # Tài liệu kiến trúc & Vận hành (01 - 07)
├── scripts/                       # Shell scripts (deploy_worker.sh, init_db.sh)
├── pyproject.toml
└── README.md
```

---

## 4. Chi Tiết Chức Năng Từng Mô-Đun

### 4.1. Domain Layer (`src/credit_agent/domain/`)
- Không chứa bất kỳ thư viện bên ngoài nào (không import Temporal, FastAPI hay SQLite).
- Định nghĩa các đối tượng trung tâm: `CreditState`, `CoApprovalOpinion`, `StatePatch`, `AuditEvent`.
- Quản lý các ngoại lệ nghiệp vụ (`NarrativeTooShortError`, `InvalidSealError`).

### 4.2. Agents Layer (`src/credit_agent/agents/`)
- Phân chia 13 Tác nhân theo 5 Stage nghiệp vụ tín dụng.
- Mỗi Agent nắm giữ logic tạo Context, quản lý System Prompt chuẩn (`prompts/`), và định dạng Structured Output.
- `registry.py` cung cấp cơ chế Dynamic Agent Loading giúp nạp Agent linh hoạt theo tên nút (`A1` -> `A13`).

### 4.3. Tools Layer (`src/credit_agent/tools/`)
- Phân tách rõ giữa `simulated/` (chạy kiểm thử/demo local) và `adapters/` (kết nối REST/gRPC tới các hệ thống thật Ngân hàng).
- `gateway.py` thực thi cơ chế **Allowlist nghiêm ngặt**: Chỉ cho phép Agent gọi đúng các Tool được cấp quyền, tự động ghi vết vi phạm vào Audit Trail.

### 4.4. Governance Layer (`src/credit_agent/governance/`)
- Độc lập hoàn toàn với AI.
- `control_gate.py`: Đánh giá quy tắc tín dụng định tính, phát hiện Hard-block không thể vượt qua.
- `integrity.py`: Tạo và xác minh Chữ ký số HMAC-SHA256 chứa `approved_amount` và các tham số cốt lõi.
- `authority.py`: Kiểm tra cấp thẩm quyền phê duyệt (CRO, Giám đốc Chi nhánh, Trưởng phòng).

### 4.5. Orchestration Layer (`src/credit_agent/orchestration/`)
- Quản lý Temporal Workflows (`CreditCoApprovalWorkflow`), Temporal Activities (`execute_agent_activity`), và Temporal Worker Process.
- Hỗ trợ cả 2 chế độ: Chạy trực tiếp trên Live Temporal Server Cluster (`127.0.0.1:7233`) hoặc Chạy In-Memory cho Test.

### 4.6. Infrastructure Layer (`src/credit_agent/infrastructure/`)
- `db/`: Triển khai Repository Pattern cho SQLite (PoC) và PostgreSQL (Production).
- `llm/`: Bọc các API LLM (Azure OpenAI, vLLM, Gemini) và sửa lỗi JSON tự động.
- `api/`: Cung cấp các RESTful API endpoints cho Web UI và các hệ thống vệ tinh.

---

## 5. Lộ Trình Di Trú Từng Bước (Migration Roadmap)

Để đảm bảo không làm gián đoạn hệ thống đang chạy, quá trình di trúc được chia thành 3 bước:

- [x] **Bước 1 (Đã hoàn thành - Phase 2 PoC)**: Tách file đơn `agents.py` và `tools.py` thành 2 gói mô-đun `agents/` và `tools/`, duy trì re-export tương thích ngược 100% tại `__init__.py`.
- [ ] **Bước 2 (Giai đoạn MVP)**: Phân tách `domain/` và `governance/` ra khỏi `models.py` và `control_gate.py`. Chuyển DB từ SQLite sang PostgreSQL.
- [ ] **Bước 3 (Giai đoạn Enterprise Go-Live)**: Tách `webui/` thành ứng dụng React/Next.js độc lập và hoàn thiện các Adapters kết nối Core Banking/CIC thật trong `tools/adapters/`.
