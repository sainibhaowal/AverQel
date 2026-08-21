from __future__ import annotations

import base64
import ipaddress
import json
from functools import lru_cache
from typing import Final, Literal
from urllib.parse import urlparse

from pydantic import Field, ValidationInfo, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ENV_ALLOWED: Final[set[str]] = {"development", "staging", "production", "test"}
PRODUCTION_ENVS: Final[set[str]] = {"production"}

DEFAULT_JWT_SECRET: Final[str] = "change-me-please-use-env-secret-min-32-chars"
DEFAULT_REFRESH_SECRET: Final[str] = "change-me-refresh-hash-secret-min-32-chars"
DEFAULT_DATABASE_URL: Final[str] = "postgresql+psycopg://postgres:postgres@localhost:1005/knowledge"
DEFAULT_MINIO_ACCESS_KEY: Final[str] = "minioadmin"
DEFAULT_MINIO_SECRET_KEY: Final[str] = "minioadmin"

REMOTE_LLM_PROVIDERS: Final[set[str]] = {
    "openai",
    "groq",
    "groq-openai-compatible",
    "mistral",
    "together",
    "fireworks",
    "perplexity",
}

# ---------------------------------------------------------------------------
# LLM Provider Presets
# ---------------------------------------------------------------------------

LLM_PROVIDER_PRESETS: dict[str, tuple[str, str]] = {
    "openai": ("https://api.openai.com/v1", "gpt-4o"),
    "groq": ("https://api.groq.com/openai/v1", "llama-3.3-70b-versatile"),
    "groq-openai-compatible": (
        "https://api.groq.com/openai/v1",
        "llama-3.3-70b-versatile",
    ),
    "mistral": ("https://api.mistral.ai/v1", "mistral-large-latest"),
    "together": (
        "https://api.together.xyz/v1",
        "meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo",
    ),
    "fireworks": (
        "https://api.fireworks.ai/inference/v1",
        "accounts/fireworks/models/llama-v3p1-70b-instruct",
    ),
    "perplexity": ("https://api.perplexity.ai", "llama-3.1-sonar-large-128k-online"),
    "ollama": ("http://localhost:11434/v1", "llama3"),
    "vllm": ("http://localhost:8000/v1", "default"),
    "lmstudio": ("http://localhost:1234/v1", "default"),
    "custom": ("", ""),
}

# Only providers known to be local-by-default belong here.
LOCAL_LLM_PROVIDERS: Final[set[str]] = {"ollama", "vllm", "lmstudio"}

# ---------------------------------------------------------------------------
# Helper Normalizers
# ---------------------------------------------------------------------------


def _normalize_str_list(values: list[str]) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []

    for item in values:
        cleaned = item.strip()
        if not cleaned:
            continue
        if cleaned in seen:
            continue
        seen.add(cleaned)
        normalized.append(cleaned)

    return normalized


def _normalize_ext_list(values: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()

    for item in values:
        cleaned = item.strip().lower()
        if not cleaned:
            continue
        if not cleaned.startswith("."):
            cleaned = f".{cleaned}"
        if cleaned in seen:
            continue
        seen.add(cleaned)
        normalized.append(cleaned)

    return normalized


def _is_http_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _is_valid_origin(value: str) -> bool:
    parsed = urlparse(value)
    return (
        parsed.scheme in {"http", "https"} and bool(parsed.netloc) and not parsed.path.rstrip("/")
    )


def _is_local_like_url(value: str) -> bool:
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower()
    return host in {"localhost", "127.0.0.1", "0.0.0.0"}  # nosec B104


def _is_private_service_host(value: str) -> bool:
    parsed = urlparse(value if "://" in value else f"http://{value}")
    host = (parsed.hostname or "").strip().lower()
    if not host:
        return False
    if host in {
        "localhost",
        "127.0.0.1",
        "0.0.0.0",
        "::1",
        "host.docker.internal",
    }:  # nosec B104 - classifier, not a bind operation
        return True
    if "." not in host:
        return True
    try:
        return ipaddress.ip_address(host).is_private
    except ValueError:
        return False


def _parse_provider_secret_keyring(raw: str | None) -> dict[str, bytes]:
    if raw is None:
        return {}

    cleaned = raw.strip()
    if not cleaned:
        return {}

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError("provider_secret_keyring_json must be valid JSON") from exc

    if not isinstance(parsed, dict) or not parsed:
        raise ValueError("provider_secret_keyring_json must be a non-empty JSON object")

    keyring: dict[str, bytes] = {}
    for kid, encoded_key in parsed.items():
        if not isinstance(kid, str) or not kid.strip():
            raise ValueError("provider secret key ids must be non-empty strings")
        if not isinstance(encoded_key, str) or not encoded_key.strip():
            raise ValueError("provider secret keys must be non-empty base64 strings")
        try:
            key_bytes = base64.urlsafe_b64decode(encoded_key.encode("utf-8"))
        except Exception as exc:  # pragma: no cover - defensive branch
            raise ValueError(f"provider secret key for kid={kid!r} is not valid base64") from exc
        if len(key_bytes) not in {16, 24, 32}:
            raise ValueError("provider secret keys must decode to 16, 24, or 32 bytes for AES-GCM")
        keyring[kid.strip()] = key_bytes
    return keyring


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="AKS_",
        case_sensitive=False,
        extra="ignore",
    )

    # -----------------------------------------------------------------------
    # App
    # -----------------------------------------------------------------------

    app_name: str = "AverQel"
    app_version: str = Field(default="1.0.0", validation_alias="AKS_APP_VERSION")
    release_version: str = Field(default="1.0.0", validation_alias="AKS_RELEASE_VERSION")
    git_sha: str = Field(default="unknown", validation_alias="AKS_GIT_SHA")
    build_timestamp_utc: str | None = Field(default=None, validation_alias="AKS_BUILD_TIMESTAMP")
    env: str = "development"
    log_level: str = "INFO"
    api_prefix: str = "/api/v1"

    # -----------------------------------------------------------------------
    # Core Infrastructure
    # -----------------------------------------------------------------------

    database_url: str = DEFAULT_DATABASE_URL
    database_pool_size: int = 8
    database_max_overflow: int = 4
    database_pool_timeout_seconds: float = 4.0
    database_statement_timeout_seconds: float = 15.0
    database_lock_timeout_seconds: float = 3.0
    redis_url: str = "redis://localhost:1010/0"

    minio_endpoint: str = "minio:9000"
    minio_access_key: str = DEFAULT_MINIO_ACCESS_KEY
    minio_secret_key: str = DEFAULT_MINIO_SECRET_KEY
    minio_secure: bool = False
    minio_verify_ssl: bool = True
    minio_bucket: str = "aks-documents"

    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:1030",
            "http://127.0.0.1:1030",
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ]
    )

    # -----------------------------------------------------------------------
    # Auth / Security
    # -----------------------------------------------------------------------

    jwt_algorithm: Literal["HS256"] = "HS256"
    jwt_secret: str = DEFAULT_JWT_SECRET
    jwt_issuer: str = "ai-knowledge-service"
    jwt_audience: str = "ai-knowledge-service-api"
    jwt_access_ttl_minutes: int = 15
    jwt_refresh_ttl_days: int = 7
    refresh_token_hash_secret: str = DEFAULT_REFRESH_SECRET

    refresh_cookie_name: str = "aks_refresh_token"
    refresh_cookie_secure: bool = True
    refresh_cookie_samesite: Literal["strict", "lax", "none"] = "strict"
    refresh_cookie_domain: str | None = None
    refresh_cookie_path: str = "/api/v1/auth"
    bootstrap_super_admin_emails: list[str] = Field(default_factory=list)

    auth_max_failed_attempts: int = 5
    auth_lockout_minutes: int = 15
    admin_break_glass_enabled: bool = False
    provider_secret_backend: Literal["env_keyring", "aws_kms"] = "env_keyring"
    provider_secret_active_kid: str | None = None
    provider_secret_keyring_json: str | None = None
    provider_secret_aws_kms_key_id: str | None = None
    provider_secret_aws_kms_region: str | None = None
    provider_secret_aws_kms_endpoint_url: str | None = None
    provider_secret_audit_reads: bool = True
    totp_secret_active_kid: str | None = None
    totp_secret_keyring_json: str | None = None
    auth_oauth_redirect_uri: str | None = None
    auth_oauth_frontend_redirect_uri: str | None = None
    auth_google_oauth_client_id: str | None = None
    auth_google_oauth_client_secret: str | None = None
    auth_github_oauth_client_id: str | None = None
    auth_github_oauth_client_secret: str | None = None
    provider_openai_oauth_enabled: bool = False
    provider_openai_oauth_official_support_verified: bool = False
    provider_openai_oauth_client_id: str | None = None
    provider_openai_oauth_redirect_uri: str | None = None
    provider_openai_oauth_allowed_redirect_uris: list[str] = Field(default_factory=list)
    provider_openai_oauth_authorize_url: str = "https://auth.openai.com/oauth/authorize"
    provider_openai_oauth_token_url: str = "https://auth.openai.com/oauth/token"
    connector_oauth_redirect_uri: str | None = None
    connector_oauth_frontend_redirect_uri: str | None = None
    connector_google_oauth_client_id: str | None = None
    connector_google_oauth_client_secret: str | None = None
    connector_github_oauth_client_id: str | None = None
    connector_github_oauth_client_secret: str | None = None
    connector_slack_oauth_client_id: str | None = None
    connector_slack_oauth_client_secret: str | None = None
    connector_notion_oauth_client_id: str | None = None
    connector_notion_oauth_client_secret: str | None = None
    # Dedicated native remote MCP OAuth credentials. These are intentionally
    # separate from connector_* settings used by existing integrations.
    mcp_google_oauth_client_id: str | None = None
    mcp_google_oauth_client_secret: str | None = None
    mcp_github_oauth_client_id: str | None = None
    mcp_github_oauth_client_secret: str | None = None
    mcp_oauth_redirect_uri: str | None = None
    mcp_catalog_max_age_seconds: int = Field(default=900, ge=60, le=86_400)
    averqel_domain: str | None = Field(default=None, validation_alias="AVERQEL_DOMAIN")
    averqel_public_origin: str | None = Field(
        default=None, validation_alias="AVERQEL_PUBLIC_ORIGIN"
    )
    livekit_url: str = Field(default="http://livekit:7880", validation_alias="LIVEKIT_URL")
    livekit_api_key: str = Field(default="devkey", validation_alias="LIVEKIT_API_KEY")
    livekit_api_secret: str = Field(
        default="cohesive-voice-secret-key-1092", validation_alias="LIVEKIT_API_SECRET"
    )

    # -----------------------------------------------------------------------
    # Upload / Parsing
    # -----------------------------------------------------------------------

    upload_max_bytes: int = 26_214_400
    tenant_max_storage_bytes: int = 1_073_741_824

    # Upload security. Production deployments must provide a reachable
    # ClamAV daemon; uploads fail closed when the scanner is unavailable.
    malware_scan_enabled: bool = True
    malware_scan_required: bool = False
    malware_scan_host: str = "clamav"
    malware_scan_port: int = 3310
    malware_scan_timeout_seconds: int = 15
    document_event_stream_ticket_ttl_seconds: int = 30

    upload_allowed_mime_types: list[str] = Field(
        default_factory=lambda: [
            "application/pdf",
            "text/plain",
            "text/markdown",
            "text/x-markdown",
            "image/png",
            "image/jpeg",
            "image/jpg",
            "image/tiff",
            "image/webp",
            "image/bmp",
            "image/gif",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "application/msword",
            "application/vnd.ms-powerpoint",
            "application/vnd.ms-excel",
            "application/vnd.ms-office",
            "application/x-ole-storage",
            "application/CDFV2",
            "application/x-cdf",
            "application/x-composite-document-file",
            "application/zip",
            "application/x-zip-compressed",
            "application/json",
            "application/xml",
            "text/xml",
            "text/csv",
            "text/tab-separated-values",
            "application/x-ipynb+json",
            "application/x-sh",
            "application/javascript",
            "application/typescript",
            "text/x-python",
            "application/octet-stream",
        ]
    )

    upload_allowed_extensions: list[str] = Field(
        default_factory=lambda: [
            ".pdf",
            ".txt",
            ".md",
            ".png",
            ".jpg",
            ".jpeg",
            ".tiff",
            ".tif",
            ".webp",
            ".bmp",
            ".gif",
            ".doc",
            ".docx",
            ".ppt",
            ".pptx",
            ".xls",
            ".xlsx",
            ".py",
            ".js",
            ".ts",
            ".java",
            ".go",
            ".rs",
            ".c",
            ".cpp",
            ".cs",
            ".php",
            ".rb",
            ".swift",
            ".kt",
            ".scala",
            ".sql",
            ".yaml",
            ".yml",
            ".json",
            ".xml",
            ".html",
            ".css",
            ".sh",
            ".toml",
            ".ini",
            ".cfg",
            ".log",
            ".csv",
            ".tsv",
            ".ipynb",
        ]
    )

    parser_max_pdf_pages: int = 1000
    parser_max_text_chars: int = 5_000_000
    legacy_conversion_enabled: bool = True
    legacy_conversion_timeout_seconds: int = 60
    extraction_low_coverage_threshold: float = 0.35

    # -----------------------------------------------------------------------
    # OCR / Vision
    # -----------------------------------------------------------------------

    ocr_enabled: bool = True
    ocr_engine: Literal["paddleocr"] = "paddleocr"
    ocr_device: Literal["cpu", "gpu"] = "cpu"
    ocr_enable_mkldnn: bool = False
    ocr_timeout_seconds: int = 20
    ocr_max_pages: int = 200
    ocr_min_confidence: float = 0.45
    ocr_languages: list[str] = Field(default_factory=lambda: ["eng"])
    pdf_image_dpi: int = 200
    ocr_retry_attempts: int = 1
    ocr_max_image_pixels: int = 25_000_000
    ocr_max_image_width: int = 10_000
    ocr_max_image_height: int = 10_000

    vision_enabled: bool = False
    vision_provider: Literal["local", "api"] = "local"
    vision_timeout_seconds: int = 20
    vision_max_pages: int = 200
    vision_retry_attempts: int = 1
    vision_cost_guard_enabled: bool = True
    vision_min_confidence: float = 0.5
    vision_tenant_allowlist: list[str] = Field(default_factory=list)

    # -----------------------------------------------------------------------
    # Ingestion / Chunking
    # -----------------------------------------------------------------------

    ingestion_max_attempts: int = 3
    ingestion_retry_backoff_seconds: int = 2

    chunk_size: int = 800
    chunk_overlap: int = 100
    chunk_min_length: int = 40

    # -----------------------------------------------------------------------
    # Embeddings / LLM
    #
    # Compatibility baseline:
    # These settings are the current env-driven provider contract used by the
    # live query and embedding runtime. Planned provider-management work must
    # remain additive until DB-backed provider selection is fully introduced.
    # -----------------------------------------------------------------------

    ai_integration_scope: Literal["embeddings_only", "embeddings_and_generation"] = (
        "embeddings_only"
    )

    embedding_dimension: int = 384
    embedding_provider: Literal[
        "local-deterministic",
        "sentence-transformers",
        "openai",
        "groq",
        "groq-openai-compatible",
        "mistral",
        "together",
        "fireworks",
        "perplexity",
        "ollama",
        "vllm",
        "lmstudio",
        "custom",
    ] = "local-deterministic"
    embedding_model: str = "intfloat/multilingual-e5-small"
    embedding_batch_size: int = 32
    embedding_normalize: bool = True
    embedding_timeout_seconds: int = 8
    embedding_retry_attempts: int = 3
    embedding_circuit_breaker_threshold: int = 3
    embedding_circuit_breaker_reset_seconds: int = 30
    local_models_root: str = "/app/models"
    local_inference_base_url: str = "http://inference:1011"
    local_inference_timeout_seconds: int = 60
    local_inference_embedding_concurrency: int = 1
    local_inference_rerank_concurrency: int = 1
    reranking_enabled: bool = True
    reranking_provider: Literal["disabled", "sentence-transformers", "cohere"] = (
        "sentence-transformers"
    )
    reranking_model: str = "BAAI/bge-reranker-v2-m3"
    reranking_timeout_seconds: int = 8
    reranking_top_k_retrieve: int = 12
    reranking_top_k_rerank: int = 8
    reranking_top_k_answer: int = 5
    local_model_warmup_enabled: bool = True

    llm_provider: Literal[
        "disabled",
        "openai",
        "groq",
        "groq-openai-compatible",
        "mistral",
        "together",
        "fireworks",
        "perplexity",
        "ollama",
        "vllm",
        "lmstudio",
        "custom",
    ] = "disabled"
    llm_model: str = ""
    llm_api_base_url: str = ""
    llm_api_key: str | None = None
    llm_temperature: float = 0.1
    llm_max_tokens_per_request: int = 1024
    llm_max_requests_per_minute: int = 30
    llm_monthly_budget_usd: float = 50.0
    llm_cost_per_1m_input_tokens_usd: float = 0.075
    llm_cost_per_1m_output_tokens_usd: float = 0.30

    @property
    def max_context_chars(self) -> int:
        """
        Backward-compatible fallback for older runtime code.

        The real context window should come from the selected provider/model.
        When that is unavailable, use a conservative estimate derived from the
        configured request token cap so existing call sites never crash.
        """
        return max(self.llm_max_tokens_per_request * 4, 4_096)

    # -----------------------------------------------------------------------
    # Query / Rate Limits / Retention
    # -----------------------------------------------------------------------

    query_top_k_min: int = 1
    query_top_k_max: int = 25
    query_cache_ttl_seconds: int = 300
    query_no_result_answer_text: str = "No relevant information found for the requested query."
    benchmark_week3_query_script_path: str = "scripts/benchmark_week3_queries.py"

    rate_limit_queries_per_user_per_minute: int = 60
    rate_limit_global_per_ip_per_5_minutes: int = 10000
    rate_limit_upload_per_user_per_5_minutes: int = 20
    rate_limit_auth_login_per_tenant_email_per_5_minutes: int = 30
    rate_limit_auth_refresh_per_ip_per_5_minutes: int = 60
    rate_limit_auth_logout_per_user_per_5_minutes: int = 60

    provider_timeout_seconds: int = 8
    provider_retry_attempts: int = 3
    provider_circuit_breaker_threshold: int = 3
    provider_circuit_breaker_reset_seconds: int = 30

    audit_log_retention_days: int = 90
    transient_record_retention_days: int = 30

    celery_task_always_eager: bool = False

    # OpenTelemetry is process instrumentation, not a runtime-selection flag.
    otel_enabled: bool = True
    otel_service_name: str = "averqel-api"
    otel_exporter_otlp_endpoint: str = "http://otel-collector:4317"
    otel_exporter_otlp_insecure: bool = True

    # -----------------------------------------------------------------------
    # Field Validators
    # -----------------------------------------------------------------------

    @field_validator("env")
    @classmethod
    def validate_env(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in ENV_ALLOWED:
            raise ValueError(f"env must be one of {sorted(ENV_ALLOWED)}")
        return normalized

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, value: str) -> str:
        allowed = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}
        normalized = value.strip().upper()
        if normalized not in allowed:
            raise ValueError(f"log_level must be one of {sorted(allowed)}")
        return normalized

    @field_validator("api_prefix", "refresh_cookie_path")
    @classmethod
    def validate_slash_prefixed_path(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned.startswith("/"):
            raise ValueError("path values must start with '/'")
        return cleaned.rstrip("/") or "/"

    @field_validator("jwt_secret", "refresh_token_hash_secret")
    @classmethod
    def validate_secret_length(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 32:
            raise ValueError("security secrets must be at least 32 characters")
        return cleaned

    @field_validator("database_url", "redis_url")
    @classmethod
    def validate_non_empty_connection_urls(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("connection URLs must not be empty")
        return cleaned

    @field_validator("minio_endpoint", "minio_bucket", "jwt_issuer", "jwt_audience", "app_name")
    @classmethod
    def validate_non_empty_strings(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("value must not be empty")
        return cleaned

    @field_validator("refresh_cookie_domain")
    @classmethod
    def validate_refresh_cookie_domain(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip().lower()
        return cleaned or None

    @field_validator("bootstrap_super_admin_emails")
    @classmethod
    def validate_bootstrap_super_admin_emails(cls, value: list[str]) -> list[str]:
        normalized = _normalize_str_list([item.lower() for item in value])
        for email in normalized:
            if "@" not in email:
                raise ValueError("bootstrap_super_admin_emails must contain valid email addresses")
        return normalized

    @field_validator("cors_origins")
    @classmethod
    def validate_cors_origins(cls, value: list[str]) -> list[str]:
        normalized = _normalize_str_list(value)
        if not normalized:
            raise ValueError("cors_origins must contain at least one origin")
        for origin in normalized:
            if not _is_valid_origin(origin):
                raise ValueError(f"Invalid CORS origin: {origin}")
        return normalized

    @field_validator("upload_allowed_mime_types")
    @classmethod
    def validate_upload_allowed_mime_types(cls, value: list[str]) -> list[str]:
        normalized = _normalize_str_list(value)
        if not normalized:
            raise ValueError("upload_allowed_mime_types must contain at least one MIME type")
        return normalized

    @field_validator("upload_allowed_extensions")
    @classmethod
    def validate_upload_allowed_extensions(cls, value: list[str]) -> list[str]:
        normalized = _normalize_ext_list(value)
        if not normalized:
            raise ValueError("upload_allowed_extensions must contain at least one extension")
        return normalized

    @field_validator("ocr_languages")
    @classmethod
    def validate_ocr_languages(cls, value: list[str]) -> list[str]:
        normalized = _normalize_str_list([item.lower() for item in value])
        if not normalized:
            raise ValueError("ocr_languages must contain at least one language")
        return normalized

    @field_validator("vision_tenant_allowlist")
    @classmethod
    def validate_vision_tenant_allowlist(cls, value: list[str]) -> list[str]:
        return _normalize_str_list(value)

    @field_validator("provider_openai_oauth_allowed_redirect_uris")
    @classmethod
    def validate_provider_openai_oauth_allowed_redirect_uris(cls, value: list[str]) -> list[str]:
        normalized = _normalize_str_list(value)
        for redirect_uri in normalized:
            parsed = urlparse(redirect_uri)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError(
                    "provider_openai_oauth_allowed_redirect_uris must contain valid http/https URLs"
                )
        return normalized

    @field_validator(
        "jwt_access_ttl_minutes",
        "jwt_refresh_ttl_days",
        "auth_max_failed_attempts",
        "auth_lockout_minutes",
        "upload_max_bytes",
        "tenant_max_storage_bytes",
        "malware_scan_port",
        "malware_scan_timeout_seconds",
        "document_event_stream_ticket_ttl_seconds",
        "legacy_conversion_timeout_seconds",
        "ocr_timeout_seconds",
        "ocr_max_pages",
        "pdf_image_dpi",
        "ocr_retry_attempts",
        "ocr_max_image_pixels",
        "ocr_max_image_width",
        "ocr_max_image_height",
        "vision_timeout_seconds",
        "vision_max_pages",
        "vision_retry_attempts",
        "ingestion_max_attempts",
        "ingestion_retry_backoff_seconds",
        "chunk_size",
        "chunk_overlap",
        "chunk_min_length",
        "embedding_dimension",
        "embedding_batch_size",
        "embedding_timeout_seconds",
        "embedding_retry_attempts",
        "embedding_circuit_breaker_threshold",
        "embedding_circuit_breaker_reset_seconds",
        "reranking_timeout_seconds",
        "reranking_top_k_retrieve",
        "reranking_top_k_rerank",
        "reranking_top_k_answer",
        "llm_max_tokens_per_request",
        "llm_max_requests_per_minute",
        "query_top_k_min",
        "query_top_k_max",
        "query_cache_ttl_seconds",
        "rate_limit_queries_per_user_per_minute",
        "rate_limit_global_per_ip_per_5_minutes",
        "rate_limit_upload_per_user_per_5_minutes",
        "rate_limit_auth_login_per_tenant_email_per_5_minutes",
        "rate_limit_auth_refresh_per_ip_per_5_minutes",
        "rate_limit_auth_logout_per_user_per_5_minutes",
        "provider_timeout_seconds",
        "provider_retry_attempts",
        "provider_circuit_breaker_threshold",
        "provider_circuit_breaker_reset_seconds",
        "audit_log_retention_days",
        "transient_record_retention_days",
    )
    @classmethod
    def validate_positive_numbers(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("numeric settings must be positive")
        return value

    @field_validator(
        "llm_monthly_budget_usd",
        "llm_cost_per_1m_input_tokens_usd",
        "llm_cost_per_1m_output_tokens_usd",
    )
    @classmethod
    def validate_positive_float_numbers(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("numeric settings must be positive")
        return value

    @field_validator("llm_temperature")
    @classmethod
    def validate_temperature(cls, value: float) -> float:
        if not 0.0 <= value <= 2.0:
            raise ValueError("llm_temperature must be between 0.0 and 2.0")
        return value

    @field_validator(
        "ocr_min_confidence",
        "vision_min_confidence",
        "extraction_low_coverage_threshold",
    )
    @classmethod
    def validate_percentage_thresholds(cls, value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError("thresholds must be between 0.0 and 1.0")
        return value

    @field_validator("query_top_k_max")
    @classmethod
    def validate_top_k_max(cls, value: int, info: ValidationInfo) -> int:
        min_value = int(info.data.get("query_top_k_min", 1))
        if value < min_value:
            raise ValueError("query_top_k_max must be greater than or equal to query_top_k_min")
        return value

    @model_validator(mode="after")
    def validate_reranking_limits(self) -> Settings:
        if self.reranking_top_k_retrieve < self.reranking_top_k_rerank:
            raise ValueError(
                "reranking_top_k_retrieve must be greater than or equal to reranking_top_k_rerank"
            )
        if self.reranking_top_k_rerank < self.reranking_top_k_answer:
            raise ValueError(
                "reranking_top_k_rerank must be greater than or equal to reranking_top_k_answer"
            )
        return self

    @field_validator("llm_api_base_url")
    @classmethod
    def validate_llm_api_base_url(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            return ""
        if not _is_http_url(cleaned):
            raise ValueError("llm_api_base_url must be a valid http/https URL")
        return cleaned.rstrip("/")

    @field_validator("connector_oauth_redirect_uri", "connector_oauth_frontend_redirect_uri")
    @classmethod
    def validate_connector_oauth_urls(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip().rstrip("/")
        if not cleaned:
            return None
        if not _is_http_url(cleaned):
            raise ValueError("connector OAuth redirect URLs must be valid http/https URLs")
        return cleaned

    @field_validator("mcp_oauth_redirect_uri")
    @classmethod
    def validate_mcp_oauth_redirect_uri(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip().rstrip("/")
        if not cleaned:
            return None
        if not _is_http_url(cleaned):
            raise ValueError("mcp_oauth_redirect_uri must be a valid http/https URL")
        return cleaned

    @field_validator(
        "llm_model",
        "llm_api_key",
        "provider_secret_active_kid",
        "provider_secret_keyring_json",
        "totp_secret_active_kid",
        "totp_secret_keyring_json",
        "provider_openai_oauth_client_id",
        "provider_openai_oauth_redirect_uri",
        "mcp_google_oauth_client_id",
        "mcp_google_oauth_client_secret",
        "mcp_github_oauth_client_id",
        "mcp_github_oauth_client_secret",
        "mcp_oauth_redirect_uri",
        "averqel_domain",
        "averqel_public_origin",
    )
    @classmethod
    def validate_optional_trimmed_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @field_validator("jwt_secret", "refresh_token_hash_secret")
    @classmethod
    def validate_min_secret_lengths(cls, value: str, info: ValidationInfo) -> str:
        cleaned = value.strip()
        if len(cleaned) < 32:
            raise ValueError(f"{info.field_name} must be at least 32 characters long")
        return cleaned

    # -----------------------------------------------------------------------
    # Model Validators
    # -----------------------------------------------------------------------

    @model_validator(mode="after")
    def resolve_llm_provider_presets(self) -> Settings:
        if self.llm_provider == "disabled":
            return self

        preset = LLM_PROVIDER_PRESETS.get(self.llm_provider)
        if preset is None:
            return self

        default_url, default_model = preset

        if not self.llm_api_base_url and default_url:
            object.__setattr__(self, "llm_api_base_url", default_url)

        if not self.llm_model and default_model:
            object.__setattr__(self, "llm_model", default_model)

        return self

    @model_validator(mode="after")
    def validate_llm_requirements(self) -> Settings:
        if self.llm_provider == "disabled":
            return self

        if self.llm_provider == "custom":
            if not self.llm_api_base_url:
                raise ValueError("llm_api_base_url is required when llm_provider=custom")
            if not self.llm_model:
                raise ValueError("llm_model is required when llm_provider=custom")

        if self.llm_provider in LOCAL_LLM_PROVIDERS:
            if not self.llm_api_base_url:
                raise ValueError(
                    f"llm_api_base_url is required for llm_provider={self.llm_provider}"
                )

        if self.ai_integration_scope == "embeddings_and_generation":
            if not self.llm_model:
                raise ValueError("llm_model is required when generation is enabled")

            if (
                self.env != "test"
                and self.llm_provider in REMOTE_LLM_PROVIDERS
                and not self.llm_api_key
            ):
                raise ValueError(
                    f"llm_api_key is required for llm_provider={self.llm_provider} "
                    "when ai_integration_scope=embeddings_and_generation"
                )

            if (
                self.llm_provider == "custom"
                and not self.llm_api_key
                and not _is_local_like_url(self.llm_api_base_url)
            ):
                raise ValueError(
                    "llm_api_key is required for llm_provider=custom when using a non-local endpoint "
                    "and ai_integration_scope=embeddings_and_generation"
                )

        return self

    @model_validator(mode="after")
    def resolve_connector_oauth_defaults(self) -> Settings:
        public_origin = (self.averqel_public_origin or "").strip().rstrip("/")
        if public_origin:
            if not self.connector_oauth_redirect_uri:
                object.__setattr__(
                    self,
                    "connector_oauth_redirect_uri",
                    f"{public_origin}/api/v1/integrations/connectors/oauth/callback",
                )
            if not self.connector_oauth_frontend_redirect_uri:
                object.__setattr__(
                    self,
                    "connector_oauth_frontend_redirect_uri",
                    f"{public_origin}/dashboard",
                )
        return self

    @model_validator(mode="after")
    def resolve_mcp_oauth_defaults(self) -> Settings:
        public_origin = (self.averqel_public_origin or "").strip().rstrip("/")
        if public_origin and not self.mcp_oauth_redirect_uri:
            object.__setattr__(
                self,
                "mcp_oauth_redirect_uri",
                f"{public_origin}{self.api_prefix}/mcp/oauth/callback",
            )
        for provider in ("google", "github"):
            client_id = getattr(self, f"mcp_{provider}_oauth_client_id")
            client_secret = getattr(self, f"mcp_{provider}_oauth_client_secret")
            if bool(client_id) != bool(client_secret):
                raise ValueError(
                    f"mcp_{provider}_oauth_client_id and mcp_{provider}_oauth_client_secret must be configured together"
                )
        return self

    @model_validator(mode="after")
    def validate_internal_consistency(self) -> Settings:
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size")

        if self.chunk_min_length > self.chunk_size:
            raise ValueError("chunk_min_length must be less than or equal to chunk_size")

        if self.refresh_cookie_samesite == "none" and not self.refresh_cookie_secure:
            raise ValueError("refresh_cookie_secure must be true when SameSite=None")

        if self.refresh_cookie_domain and self.refresh_cookie_domain.startswith("."):
            object.__setattr__(
                self, "refresh_cookie_domain", self.refresh_cookie_domain.lstrip(".")
            )

        if (
            self.vision_enabled
            and self.vision_provider == "api"
            and not self.vision_cost_guard_enabled
        ):
            raise ValueError(
                "vision_cost_guard_enabled must remain true when vision_enabled=true "
                "and vision_provider=api"
            )

        if (
            self.vision_enabled
            and self.vision_provider == "api"
            and not self.vision_tenant_allowlist
        ):
            raise ValueError(
                "vision_tenant_allowlist must not be empty when vision_enabled=true and vision_provider=api"
            )

        return self

    @model_validator(mode="after")
    def validate_production_hardening(self) -> Settings:
        if self.env not in PRODUCTION_ENVS:
            return self

        if self.jwt_secret == DEFAULT_JWT_SECRET:
            raise ValueError("Production requires a non-default jwt_secret")

        if self.refresh_token_hash_secret == DEFAULT_REFRESH_SECRET:
            raise ValueError("Production requires a non-default refresh_token_hash_secret")

        if self.database_url == DEFAULT_DATABASE_URL:
            raise ValueError("Production requires a non-default database_url")

        if self.minio_access_key == DEFAULT_MINIO_ACCESS_KEY:
            raise ValueError("Production requires a non-default minio_access_key")

        if self.minio_secret_key == DEFAULT_MINIO_SECRET_KEY:
            raise ValueError("Production requires a non-default minio_secret_key")

        if not self.refresh_cookie_secure:
            raise ValueError("Production requires refresh_cookie_secure=true")

        if self.minio_secure is False and not _is_private_service_host(self.minio_endpoint):
            raise ValueError(
                "Production requires minio_secure=true unless minio_endpoint is an internal private service"
            )

        if not self.connector_oauth_redirect_uri:
            raise ValueError("Production requires connector_oauth_redirect_uri")

        if not self.connector_oauth_frontend_redirect_uri:
            raise ValueError("Production requires connector_oauth_frontend_redirect_uri")

        if not self.connector_oauth_redirect_uri.startswith("https://"):
            raise ValueError("Production requires connector_oauth_redirect_uri to use https")

        if not self.connector_oauth_frontend_redirect_uri.startswith("https://"):
            raise ValueError(
                "Production requires connector_oauth_frontend_redirect_uri to use https"
            )

        if not self.malware_scan_enabled or not self.malware_scan_required:
            raise ValueError("Production requires malware scanning to be enabled and required")
        if not self.malware_scan_host.strip():
            raise ValueError("Production requires malware_scan_host")

        if self.mcp_oauth_redirect_uri and not self.mcp_oauth_redirect_uri.startswith("https://"):
            raise ValueError("Production requires mcp_oauth_redirect_uri to use https")

        if self.llm_provider in REMOTE_LLM_PROVIDERS and not self.llm_api_key:
            raise ValueError(
                f"Production requires llm_api_key for llm_provider={self.llm_provider}"
            )

        if (
            self.llm_provider == "custom"
            and self.llm_api_base_url
            and not _is_local_like_url(self.llm_api_base_url)
            and not self.llm_api_key
        ):
            raise ValueError("Production requires llm_api_key for non-local custom LLM endpoints")

        if (
            self.provider_secret_backend == "env_keyring"  # nosec B105
        ):  # backend selector, not a secret
            if not self.provider_secret_active_kid:
                raise ValueError("Production requires provider_secret_active_kid")

            if not self.provider_secret_keyring_json:
                raise ValueError("Production requires provider_secret_keyring_json")

            keyring = _parse_provider_secret_keyring(self.provider_secret_keyring_json)
            if self.provider_secret_active_kid not in keyring:
                raise ValueError(
                    "provider_secret_active_kid must exist in provider_secret_keyring_json"
                )
        elif not self.provider_secret_aws_kms_key_id:
            raise ValueError("Production requires provider_secret_aws_kms_key_id")

        return self

    @model_validator(mode="after")
    def validate_provider_openai_oauth_gate(self) -> Settings:
        if not self.provider_openai_oauth_enabled:
            return self

        if not self.provider_openai_oauth_official_support_verified:
            raise ValueError(
                "provider_openai_oauth_enabled requires provider_openai_oauth_official_support_verified=true"
            )

        if not self.provider_openai_oauth_client_id:
            raise ValueError(
                "provider_openai_oauth_client_id is required when provider_openai_oauth_enabled=true"
            )

        if not self.provider_openai_oauth_redirect_uri:
            raise ValueError(
                "provider_openai_oauth_redirect_uri is required when provider_openai_oauth_enabled=true"
            )

        if not self.provider_openai_oauth_allowed_redirect_uris:
            raise ValueError(
                "provider_openai_oauth_allowed_redirect_uris must not be empty when provider_openai_oauth_enabled=true"
            )

        redirect_uri = self.provider_openai_oauth_redirect_uri.rstrip("/")
        allowlisted = {
            item.rstrip("/") for item in self.provider_openai_oauth_allowed_redirect_uris
        }
        if redirect_uri not in allowlisted:
            raise ValueError(
                "provider_openai_oauth_redirect_uri must be included in provider_openai_oauth_allowed_redirect_uris"
            )

        return self

    @model_validator(mode="after")
    def validate_provider_secret_keyring(self) -> Settings:
        if self.provider_secret_backend == "aws_kms":  # nosec B105 - backend selector, not a secret
            if self.provider_secret_active_kid or self.provider_secret_keyring_json:
                raise ValueError(
                    "provider_secret_active_kid/provider_secret_keyring_json are not used when provider_secret_backend=aws_kms"
                )
            if not self.provider_secret_aws_kms_key_id:
                raise ValueError(
                    "provider_secret_aws_kms_key_id is required when provider_secret_backend=aws_kms"
                )
            return self

        has_active_kid = bool(self.provider_secret_active_kid)
        has_keyring = bool(self.provider_secret_keyring_json)

        if has_active_kid != has_keyring:
            raise ValueError(
                "provider_secret_active_kid and provider_secret_keyring_json must be set together"
            )

        if not has_keyring:
            return self

        keyring = _parse_provider_secret_keyring(self.provider_secret_keyring_json)
        if self.provider_secret_active_kid not in keyring:
            raise ValueError(
                "provider_secret_active_kid must exist in provider_secret_keyring_json"
            )

        return self

    @model_validator(mode="after")
    def validate_totp_secret_keyring(self) -> Settings:
        has_active_kid = bool(self.totp_secret_active_kid)
        has_keyring = bool(self.totp_secret_keyring_json)

        if has_active_kid != has_keyring:
            raise ValueError(
                "totp_secret_active_kid and totp_secret_keyring_json must be set together"
            )

        if not has_keyring:
            return self

        keyring = _parse_provider_secret_keyring(self.totp_secret_keyring_json)
        if self.totp_secret_active_kid not in keyring:
            raise ValueError("totp_secret_active_kid must exist in totp_secret_keyring_json")

        return self

    @property
    def effective_totp_secret_active_kid(self) -> str | None:
        return self.totp_secret_active_kid or self.provider_secret_active_kid

    @property
    def effective_totp_secret_keyring_json(self) -> str | None:
        return self.totp_secret_keyring_json or self.provider_secret_keyring_json


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
