# 08. Thiết Kế Hạ Tầng & Quy Hoạch Năng Lực (Sizing Guide) Enterprise

---

## 1. Mục Đích & Phạm Vi

Tài liệu này quy hoạch chi tiết **Hạ tầng Kỹ thuật & Sizing Năng lực (Capacity Planning)** cho hệ thống **CreditAgent (Luồng Thẩm Định Tín Dụng Đa Tác Nhân Có Kiểm Soát)** khi triển khai quy mô Enterprise tại Ngân hàng với công suất **10.000 hồ sơ / giao dịch cần thẩm định một ngày**.

---

## 2. Bài Toán Tải & Tính Toán Năng Lực (Capacity Calculation)

### 2.1. Giả định Vận hành Tín dụng Ngân hàng
- **Tổng số hồ sơ xử lý**: 10.000 hồ sơ / ngày.
- **Thời gian xử lý cao điểm**: 8 giờ làm việc hành chính (8h30 – 16h30).
- **Hệ số tải đỉnh (Peak Factor)**: $3.0\times - 5.0\times$ (dành cho khung giờ đầu buổi sáng và đầu buổi chiều).

### 2.2. Tính toán Tốc độ Giao dịch (TPS - Transactions Per Second)

$$\text{TPS Trung bình} = \frac{10.000 \text{ hồ sơ}}{8 \times 3.600 \text{ giây}} \approx \mathbf{0.35 \text{ - } 0.5 \text{ hồ sơ/giây}}$$

$$\text{Peak TPS (Giờ cao điểm)} = 0.5 \times 4 \approx \mathbf{1.5 \text{ - } 2.5 \text{ hồ sơ/giây}}$$

*(Tương đương hệ thống phải tiếp nhận và xử lý đồng thời 2-3 hồ sơ tín dụng mới phát sinh mỗi giây ở thời điểm cao điểm).*

### 2.3. Khối lượng Yêu cầu tới AI Agent & Backend API

Mỗi hồ sơ thẩm định tín dụng SME trải qua **13 AI Agents (A1–A13)** và trung bình **~32 lượt gọi Tool API**:

| Chỉ số | Khối lượng / Ngày | Khối lượng Giờ cao điểm (Peak / Second) |
| :--- | :--- | :--- |
| **Tổng số lượt gọi LLM Agent** | $10.000 \times 13 = \mathbf{130.000 \text{ calls/ngày}}$ | **15 – 30 LLM requests / giây** |
| **Tổng số lượt gọi Tool API** | $10.000 \times 32 = \mathbf{320.000 \text{ calls/ngày}}$ | **40 – 80 API requests / giây** |
| **Tổng dung lượng Audit Log** | ~3,5 GB JSON logs/ngày | ~150 KB/giây |

---

## 3. Cấu Hình Hạ Tầng Chi Tiết (Infrastructure Hardware Sizing)

Dựa trên con số **Peak 2.5 TPS**, dưới đây là bảng quy hoạch tài nguyên máy chủ (Hardware Sizing Guide) cho 3 môi trường:

```
                                  ┌──────────────────────────┐
                                  │   NLB / F5 Load Balancer │
                                  └────────────┬─────────────┘
                                               │
                                               ▼
                                  ┌──────────────────────────┐
                                  │ K8s Ingress Controller   │
                                  └────────────┬─────────────┘
                                               │
               ┌───────────────────────────────┴───────────────────────────────┐
               ▼                                                               ▼
 ┌──────────────────────────┐                                    ┌──────────────────────────┐
 │ Web UI / API Pods (x3)   │                                    │ Temporal Workers (x5)    │
 └─────────────┬────────────┘                                    └─────────────┬────────────┘
               │                                                               │
               ├───────────────────────────────┐                               │
               ▼                               ▼                               ▼
 ┌──────────────────────────┐    ┌──────────────────────────┐    ┌──────────────────────────┐
 │ PostgreSQL Database      │    │ Redis Cluster            │    │ Temporal Server Cluster  │
 │ (Primary + Replica)      │    │ (Semantic Cache)         │    │ (3 Nodes + Postgres)     │
 └──────────────────────────┘    └──────────────────────────┘    └──────────────────────────┘
                                                                               │
                                                                               ▼
                                                                 ┌──────────────────────────┐
                                                                 │ Enterprise LLM Serving   │
                                                                 │ (Azure OpenAI / vLLM GPU)│
                                                                 └──────────────────────────┘
```

### 3.1. Tầng Điều phối Temporal Cluster (Backbone Orchestration Engine)
- **Số lượng Node**: 3 Nodes (Đảm bảo High Availability - HA).
- **Cấu hình mỗi Node**: 4 vCPU, 8 GB RAM, SSD 100 GB.
- **Database cho Temporal State**: PostgreSQL Dedicated (4 vCPU, 16 GB RAM, SSD NVMe 200 GB).

### 3.2. Tầng Thực thi CreditAgent Workers (Kubernetes Auto-scaling Cluster)
- **Môi trường**: Kubernetes (K8s) Pods chạy Python 3.9+.
- **Số lượng Pods cơ sở**: 3 Pods (Auto-scaling HPA tự động mở rộng lên **10 Pods** khi queue dài).
- **Cấu hình mỗi Pod**: 4 vCPU, 8 GB RAM.

### 3.3. Tầng Cơ sở Dữ liệu Nghiệp vụ (Credit State & Audit Repository)
- **Công nghệ**: PostgreSQL 15+ Enterprise Cluster.
- **Node Chính (Primary)**: 8 vCPU, 32 GB RAM, SSD NVMe 500 GB (Storage High IOPS).
- **Node Phụ (Read Replica)**: 4 vCPU, 16 GB RAM (Dành cho Báo cáo Analytics & Dashboard).
- **Connection Pooler**: PgBouncer (Cho phép tối đa 1.000 kết nối đồng thời).

### 3.4. Tầng Caching & Session (Redis Cluster)
- **Cấu hình**: 3 Master - 3 Replica Redis Nodes (Mỗi node 2 vCPU, 8 GB RAM).
- **Nhiệm vụ**:
  - Lưu **Semantic LLM Cache** (Caching kết quả câu trả lời cho các prompt lặp lại).
  - Cache dữ liệu tra cứu CIC (Thời gian lưu 30 ngày).
  - Quản lý Session của Cán bộ Phê duyệt.

### 3.5. Tầng LLM Serving (Lựa chọn 1 trong 2 Phương án)

#### 🔹 Phương án A: Sử dụng Cloud Enterprise API (Azure OpenAI / AWS Bedrock)
- **Hạn mức cần đăng ký**: **Provisioned Throughput (PTU)** khoảng **400 – 600 TPM (Transactions Per Minute)**.
- **Độ trễ kỳ vọng**: 1,2s – 2,5s / request.

#### 🔹 Phương án B: Tự Host Private LLM On-Premise (Qwen2.5-72B / Llama-3.3-70B)
- **Hạ tầng GPU**: 1 Server GPU trang bị **4x GPU NVIDIA A100 (80GB)** hoặc **2x NVIDIA H100**.
- **LLM Engine**: **vLLM** hoặc **TensorRT-LLM** cấu hình Tensor Parallelism = 4.
- **Độ trễ kỳ vọng**: **250ms – 500ms / request** (Nhanh gấp 5 lần Cloud API).

---

## 4. Tổng Hợp Bảng Sizing Tài Nguyên Toàn Hệ Thống

| Thành phần Hạ tầng | Số lượng | Cấu hình vCPU / GPU | RAM | Storage |
| :--- | :--- | :--- | :--- | :--- |
| **Temporal Server Cluster** | 3 Nodes | 4 vCPU / node | 8 GB / node | 100 GB SSD |
| **Temporal Postgres DB** | 1 Primary | 4 vCPU | 16 GB | 200 GB NVMe |
| **CreditAgent K8s Workers** | 3 – 10 Pods | 4 vCPU / pod | 8 GB / pod | Ephemeral |
| **CreditAgent Postgres DB** | 1 Primary + 1 Replica | 8 vCPU (Primary) | 32 GB | 500 GB NVMe |
| **Redis Cluster** | 6 Nodes (HA) | 2 vCPU / node | 8 GB / node | 50 GB SSD |
| **Private LLM Server (Option B)** | 1 Server | **4x GPU NVIDIA A100** | 256 GB | 1 TB NVMe |

---

## 5. Chiến Lược Khắc Phục Nút Thắt & Tối Ưu Hiệu Năng (Optimization Strategies)

### 5.1. Tối ưu LLM Latency via Semantic Caching
Hệ thống sử dụng **Redis Vector Search** để lưu vết các truy vấn của Agent:
- Với các dữ liệu nạp lại hoặc hồ sơ tái cấp hạn mức, kết quả trích xuất BCTC hay tra cứu CIC cũ được trả về ngay trong **< 10ms** mà không cần gọi lại LLM.
- Giúp giảm **25% – 35% tổng số lượt gọi LLM** mỗi ngày.

### 5.2. Phân luồng Hàng đợi Temporal (Priority Queues)
Tách `credit-approval-queue` thành 3 hàng đợi riêng biệt:
1. `fast-tools-queue`: Xử lý công cụ gọi API ngân hàng (Latency < 200ms).
2. `heavy-llm-queue`: Xử lý các Agent gọi LLM đắt đỏ (A6, A7, A8, A10, A11, A12).
3. `vip-priority-queue`: Hàng đợi ưu tiên xử lý tức thì cho hồ sơ Doanh nghiệp Lớn / VIP.

### 5.3. Circuit Breaker & Fallback cho Tool API Ngân hàng
Khi hệ thống tra cứu CIC hoặc Core Banking gặp sự cố gián đoạn (Timeout / HTTP 503):
- Cổng **ToolGateway** tự động kích hoạt **Circuit Breaker** (Trạng thái OPEN).
- Chuyển tiếp kết quả về dạng `PARTIAL_DATA` để Agent A1/A2 ghi nhận Data Gap thay vì treo luồng Workflow.

---

## 6. Kế Hoạch Dự Phòng & Sẵn Sàng Cao (HA / DR)

1. **Multi-AZ Deployment**: Tất cả các dịch vụ (K8s Pods, Temporal, Postgres, Redis) được triển khai phân tán trên ít nhất **2 Availability Zones (AZ)** trong Data Center Ngân hàng.
2. **Continuous Database Backup**: PostgreSQL sử dụng cơ chế **WAL Archiving (pgBackRest)** cho phép khôi phục dữ liệu về bất kỳ thời điểm nào trong quá khứ (Point-in-Time Recovery - PITR) với chỉ số **RPO < 1 phút**.
3. **Disaster Recovery (DR) RTO/RPO**:
   - **RPO (Recovery Point Objective)**: < 1 phút.
   - **RTO (Recovery Time Objective)**: < 15 phút khi chuyển vùng dữ liệu sang Data Center dự phòng.
