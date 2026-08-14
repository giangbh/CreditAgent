# 03. Danh Mục 25 Backend Tools & Bảng Mapping Hệ Thống Ngân Hàng

---

## 1. Bảng Mapping 25 Tools với các Hệ thống Backend Ngân hàng

| STT | Tên Tool trong Codebase | Agent được phép dùng | Hệ thống Backend đảm nhiệm | Chức năng nghiệp vụ chính |
| :--- | :--- | :--- | :--- | :--- |
| **1** | `document_inventory` | A1 | **DMS / ECM** *(Document Management)* | Lấy danh mục tất cả tài liệu chứng từ trong hồ sơ khoản vay. |
| **2** | `classify_document` | A1 | **DMS / OCR Engine** | Phân loại tự động tài liệu (BCTC, GPKD, Sao kê, CCCD, TSBĐ). |
| **3** | `extract_document_fields` | A1 | **DMS / OCR Extract Service** | Trích xuất các trường dữ liệu quan trọng (Doanh thu khai báo, MST, Hạn mức vay xin cấp). |
| **4** | `parse_bank_statement` | A1 | **Statement Parser Engine** | Đọc, bóc tách cấu trúc file sao kê ngân hàng & kiểm tra cân đối số dư. |
| **5** | `resolve_borrower_identity` | A1 | **Core Banking (CBS) / CIF** | Đối soát danh tính bên vay với CSDL Thông tin khách hàng ngân hàng. |
| **6** | `validate_case_completeness` | A1 | **LOS** *(Loan Originating System)* | Kiểm tra tính đầy đủ của bộ hồ sơ theo danh mục chứng từ bắt buộc. |
| **7** | `query_transactions` | A2, A3 | **Core Banking / Transaction DB** | Truy vấn dữ liệu giao dịch chi tiết từ tài liệu sao kê / tài khoản thanh toán. |
| **8** | `compute_cashflow_metrics` | A2 | **Cashflow Analytics Service** | Tính toán chỉ số dòng tiền (Tổng Inflow/Outflow, độ tập trung khách hàng). |
| **9** | `detect_cashflow_anomalies` | A2 | **Cashflow Analytics / AI Engine** | Phát hiện bất thường dòng tiền (Phụ thuộc 1 khách hàng >45%, sụt giảm đột ngột). |
| **10** | `build_entity_transaction_graph` | A3 | **Graph DB** *(Neo4j / Memgraph)* | Xây dựng đồ thị giao dịch liên kết giữa bên vay và các bên liên quan. |
| **11** | `detect_transaction_cycles` | A3 | **Anti-Fraud / Graph Analytics** | Quét và tính điểm rủi ro dòng tiền vòng tròn (Circular funds score) & pass-through. |
| **12** | `trace_funds` | A3 | **Graph DB / AML Engine** | Truy vết đường đi vật lý của các dòng tiền lớn qua các tài khoản. |
| **13** | `reconcile_declared_revenue` | A4 | **Financial Spreading Engine** | Đối soát Doanh thu khai báo trên BCTC vs Doanh thu thực tế qua sao kê. |
| **14** | `calculate_credit_capacity` | A4, A9 | **Financial Rating & Capacity Engine**| Tính hạn mức tín dụng cấp tối đa dựa trên DSCR & Dòng tiền thực tế. |
| **15** | `stress_repayment_capacity` | A4, A9 | **Risk Stress-Test Engine** | Giả lập kịch bản stress-test khả năng trả nợ (ví dụ: Doanh thu giảm 22%). |
| **16** | `assess_refinancing_pattern` | A4 | **EWS** *(Early Warning System)* | Đánh giá rủi ro đảo nợ / tái cấp vốn khi chưa chứng minh được nguồn trả nợ. |
| **17** | `search_policy` | A5 | **Policy RAG / Vector DB** | Tìm kiếm văn bản quy định/chính sách tín dụng SME phù hợp với sản phẩm. |
| **18** | `get_policy_clause` | A5 | **BRE / Policy Management System**| Trích xuất chi tiết điều khoản chính sách tín dụng (hạn mức, kỳ hạn, điều kiện). |
| **19** | `evaluate_policy_rule` | A5, A9 | **BRE** *(Business Rule Engine)* | Đánh giá quy tắc tuân thủ (Phát hiện vi phạm tenor, vi phạm rủi ro dòng tiền). |
| **20** | `validate_policy_citation` | A5 | **BRE / Legal Compliance** | Kiểm tra tính hiệu lực và trích dẫn văn bản pháp lý chính xác. |
| **21** | `resolve_approval_authority` | A5, A9 | **LOS / Authority Matrix System** | Xác định cấp phê duyệt có thẩm quyền (Giám đốc Chi nhánh vs CRO/Hội sở). |
| **22** | `calculate_amortization` | A9 | **Core Banking / Amortization Engine**| Tính toán chi tiết lịch trả nợ gốc/lãi theo tenor và phương thức vay. |
| **23** | `resolve_pricing_band` | A9 | **Pricing & Tariff System** | Xác định khung lãi suất & phí áp dụng theo phân hạng rủi ro (Risk-based pricing). |
| **24** | `validate_deal_structure` | A9 | **LOS Validation Engine** | Kiểm tra tính hợp lệ của cấu trúc đề xuất vay trước khi trình phê duyệt. |
| **25** | `retrieve_approved_memory` | *(Nâng cấp)*| **Enterprise Knowledge Memory** | Truy vấn lịch sử các ngoại lệ / quyết định tín dụng tương tự đã được duyệt trước đó. |

---

## 2. Thông tin Yêu cầu Sẵn sàng (Data Readiness) cho từng Hệ thống Backend

Để 25 Tools trên khai thác mượt mà trong môi trường Production, mỗi hệ thống Backend cần chuẩn bị dữ liệu & API Contracts theo tiêu chuẩn sau:

### 🟢 1. DMS / ECM (Hệ thống Quản lý Tài liệu & OCR)
- **Cần chuẩn bị sẵn:**
  - File tài liệu gốc dưới dạng PDF/Image kèm mã băm Checksum SHA-256 (chống sửa đổi).
  - Dữ liệu OCR cấu trúc JSON (Bounding box, text, confidence score từng trường).
  - Trạng thái kiểm duyệt tài liệu (`PENDING`, `VALID`, `REJECTED`).
  - API endpoint trả về danh mục hồ sơ theo `application_id`.

### 🔵 2. Core Banking (CBS) & Dữ liệu CIF / Sao kê
- **Cần chuẩn bị sẵn:**
  - Hồ sơ CIF chuẩn hóa của Doanh nghiệp & Người đại diện (MST, ĐKKD, Mã CIF).
  - Dữ liệu Lịch sử Giao dịch chi tiết theo dòng (Transaction Ledger: Ngày giao dịch, Số tiền, Dấu ghi Nợ/Có, Số tài khoản đối ứng, Tên bên đối ứng, Nội dung chuyển tiền).
  - Trạng thái tài khoản (Đang hoạt động, Phong tỏa, Nợ quá hạn).

### 🔴 3. Graph Database & Anti-Fraud Engine (Neo4j / Memgraph)
- **Cần chuẩn bị sẵn:**
  - Mô hình đồ thị (Node: Doanh nghiệp/Cá nhân/Tài khoản; Edge: Giao dịch chuyển tiền).
  - API tính toán sẵn chỉ số **Circular Flow Score** (từ 0.0 - 1.0) và chuỗi node nạp/rút liên hoàn.
  - Thông tin gắn nhãn bên liên quan (Related-party mapping: Cùng chủ sở hữu, cùng địa chỉ, cùng kế toán).

### 🟡 4. Financial Spreading & Stress-Test Engine
- **Cần chuẩn bị sẵn:**
  - BCTC đã trải phổ (Spreading Balance Sheet, P&L, Cashflow Statement).
  - Bộ công thức tài chính đã chuẩn hóa theo quy định Ngân hàng (DSCR, ICR, Working Capital Gap).
  - Tham số Kịch bản Stress-Test (Tỷ lệ sụt giảm doanh thu, Biến động lãi suất chuẩn của Ngân hàng).

### 🟣 5. Policy RAG Vector DB & BRE (Business Rule Engine)
- **Cần chuẩn bị sẵn:**
  - CSDL Văn bản Chính sách Tín dụng đã được Chunking & Vectorize Embeddings (kèm metadata: Mã văn bản, Ngày hiệu lực, Sản phẩm áp dụng, Cấp ban hành).
  - Ma trận Phân cấp Thẩm quyền phê duyệt (Ma trận Hạn mức + Loại ngoại lệ).
  - Tập luật Rule Engine xác định (Hard Rules vs Advisory Rules).

### 🟠 6. LOS (Loan Originating System) & Pricing Engine
- **Cần chuẩn bị sẵn:**
  - Metadata Đơn xin vay (Application ID, Sản phẩm vay, Hạn mức đề xuất, Tenor, Phương thức trả nợ).
  - Ma trận Định giá Tín dụng dựa trên Rủi ro (Risk-Based Pricing Matrix: Hạng Rủi ro A/B/C -> Lãi suất cơ sở + Biên độ).
  - Lịch trả nợ mẫu (Amortization Schedule formula).
