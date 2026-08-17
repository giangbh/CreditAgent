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


CONFIG = AppConfig()
