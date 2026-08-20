import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


def _load_env_file() -> None:
    """Auto-loads key-value pairs from .env or .env.local into os.environ if not already set."""
    pkg_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(os.path.dirname(os.path.dirname(pkg_dir)))
    candidates = [
        os.path.join(root_dir, ".env"),
        os.path.join(root_dir, ".env.local"),
        os.path.join(os.getcwd(), ".env") if hasattr(os, "getcwd") else "",
    ]
    for env_path in candidates:
        if env_path and os.path.isfile(env_path):
            try:
                with open(env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#") or "=" not in line:
                            continue
                        key, val = line.split("=", 1)
                        key = key.strip()
                        val = val.strip().strip("'\"")
                        if key and key not in os.environ:
                            os.environ[key] = val
            except Exception:
                pass


_load_env_file()


@dataclass
class AppConfig:
    # Temporal Server & Engine Configuration
    TEMPORAL_HOST: str = os.getenv("TEMPORAL_HOST", "127.0.0.1")
    TEMPORAL_PORT: int = int(os.getenv("TEMPORAL_PORT", "7233"))
    TEMPORAL_TARGET_HOST: str = os.getenv("TEMPORAL_TARGET_HOST", f"{os.getenv('TEMPORAL_HOST', '127.0.0.1')}:{os.getenv('TEMPORAL_PORT', '7233')}")
    TEMPORAL_UI_URL: str = os.getenv("TEMPORAL_UI_URL", "http://localhost:8233")
    TEMPORAL_TASK_QUEUE: str = os.getenv("TEMPORAL_TASK_QUEUE", "credit-approval-queue")
    TEMPORAL_WORKER_COUNT: int = int(os.getenv("TEMPORAL_WORKER_COUNT", "4"))

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

    # Distributed Claim Check & Cache Configuration (Multi-Tier: L1 RAM -> L2 Redis -> L3 DB)
    REDIS_URL: Optional[str] = os.getenv("REDIS_URL", None)
    CLAIM_CHECK_TTL_SECONDS: int = int(os.getenv("CLAIM_CHECK_TTL_SECONDS", "604800"))  # 7 days
    CLAIM_CHECK_STORE_TYPE: str = os.getenv("CLAIM_CHECK_STORE_TYPE", "TIERED")  # "MEMORY", "REDIS", "TIERED"

    # DeepSeek & Enterprise LLM Configuration (Loaded from .env / ENV)
    DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", os.getenv("CREDIT_AGENT_LLM_API_KEY", ""))
    DEEPSEEK_BASE_URL: str = os.getenv("DEEPSEEK_BASE_URL", os.getenv("CREDIT_AGENT_LLM_BASE_URL", "https://api.deepseek.com")).rstrip("/")
    DEEPSEEK_MODEL: str = os.getenv("DEEPSEEK_MODEL", os.getenv("CREDIT_AGENT_LLM_MODEL", "deepseek-chat"))
    DEEPSEEK_TIMEOUT_SEC: float = float(os.getenv("DEEPSEEK_TIMEOUT_SEC", "90.0"))


CONFIG = AppConfig()
