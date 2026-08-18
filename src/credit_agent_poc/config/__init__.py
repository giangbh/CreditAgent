import os
from dataclasses import dataclass


@dataclass
class AppConfig:
    # Temporal Server & Engine Configuration
    TEMPORAL_HOST: str = os.getenv("TEMPORAL_HOST", "127.0.0.1")
    TEMPORAL_PORT: int = int(os.getenv("TEMPORAL_PORT", "7233"))
    TEMPORAL_TARGET_HOST: str = os.getenv("TEMPORAL_TARGET_HOST", f"{os.getenv('TEMPORAL_HOST', '127.0.0.1')}:{os.getenv('TEMPORAL_PORT', '7233')}")
    TEMPORAL_UI_URL: str = os.getenv("TEMPORAL_UI_URL", "http://localhost:8233")
    TEMPORAL_TASK_QUEUE: str = os.getenv("TEMPORAL_TASK_QUEUE", "credit-approval-queue")

    # Web Server & Persistence Configuration
    WEB_HOST: str = os.getenv("WEB_HOST", "127.0.0.1")
    WEB_PORT: int = int(os.getenv("WEB_PORT", "8080"))
    DB_PATH: str = os.getenv("DB_PATH", "credit_agent.db")

    # Real Production Enterprise Backend Endpoints
    BACKEND_MODE: str = os.getenv("BACKEND_MODE", "MOCK")  # "MOCK" or "PRODUCTION"
    CBS_ENDPOINT_URL: str = os.getenv("CBS_ENDPOINT_URL", "https://cbs.internal.bank.vn/api/v1")
    DMS_OCR_ENDPOINT_URL: str = os.getenv("DMS_OCR_ENDPOINT_URL", "https://dms-ocr.internal.bank.vn/api/v1")
    CIC_ENDPOINT_URL: str = os.getenv("CIC_ENDPOINT_URL", "https://cic-gateway.internal.bank.vn/api/v1")
    GRAPH_FRAUD_ENDPOINT_URL: str = os.getenv("GRAPH_FRAUD_ENDPOINT_URL", "https://graph-fraud.internal.bank.vn/api/v1")
    POLICY_BRE_ENDPOINT_URL: str = os.getenv("POLICY_BRE_ENDPOINT_URL", "https://policy-bre.internal.bank.vn/api/v1")
    LOS_STRUCTURING_ENDPOINT_URL: str = os.getenv("LOS_STRUCTURING_ENDPOINT_URL", "https://los.internal.bank.vn/api/v1")
    BACKEND_API_KEY: str = os.getenv("BACKEND_API_KEY", "")
    BACKEND_TIMEOUT_SEC: float = float(os.getenv("BACKEND_TIMEOUT_SEC", "10.0"))


CONFIG = AppConfig()
