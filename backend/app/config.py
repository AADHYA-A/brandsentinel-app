from __future__ import annotations
import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BS_", env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./data/brandsentinel.db"
    data_dir: str = "./data"
    secret_key: str = "dev-only-change-me-dev-only-change-me"
    encryption_key: str = ""            # Fernet key; auto-created in data_dir for dev
    token_minutes: int = 60 * 8

    # AI layer (optional). Without a key every check is deterministic or rule-based.
    llm_api_key: str = os.environ.get("ANTHROPIC_API_KEY", "")
    llm_model: str = "claude-sonnet-5-5"
    llm_url: str = "https://api.anthropic.com/v1/messages"
    llm_timeout: float = 8.0
    ai_enabled: bool = True
    tenant_local_only: bool = False     # tenant-wide switch: never call an external model

    # Auth
    dev_login: bool = True              # password login with seeded demo users
    seed_demo: bool = True
    demo_password: str = "demo123"
    oidc_issuer: str = ""               # set to enable OAuth2/OIDC bearer tokens
    oidc_audience: str = ""
    oidc_role_claim: str = "role"
    oidc_tenant_claim: str = "tenant"

    # Storage: local filesystem by default, S3-compatible when a bucket is set
    s3_bucket: str = ""
    s3_endpoint: str = ""
    max_upload_mb: int = 10
    cors_origins: str = "http://localhost:5173"
    rate_limit_per_min: int = 60
    default_tenant: str = "lumora"

    @property
    def data_path(self) -> Path:
        p = Path(self.data_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p


settings = Settings()
