from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StorageUsageSchema(BaseModel):
    documents_bytes: int = Field(ge=0)
    library_bytes: int = Field(ge=0)
    artifacts_bytes: int = Field(ge=0)
    pending_upload_bytes: int = Field(ge=0)
    account_data_bytes: int = Field(default=0, ge=0)
    total_bytes: int = Field(ge=0)

    model_config = ConfigDict(extra="forbid")


class PlanCardSchema(BaseModel):
    id: str
    name: str
    storage_limit_bytes: int = Field(ge=0)
    description: str
    features: list[str]
    admin_only: bool = False

    model_config = ConfigDict(extra="forbid")


class CurrentPlanSchema(BaseModel):
    id: str
    name: str
    storage_limit_bytes: int = Field(ge=0)
    description: str
    admin_account: bool

    model_config = ConfigDict(extra="forbid")


class BetaNoticeSchema(BaseModel):
    """Config-driven beta grant notice. `enabled` is False for admins."""

    enabled: bool = False
    plan_id: str = "free"
    plan_name: str = ""
    resurface_hours: int = 36

    model_config = ConfigDict(extra="forbid")


class PlansResponse(BaseModel):
    current_plan: CurrentPlanSchema
    usage: StorageUsageSchema
    plans: list[PlanCardSchema]
    storage_scope: str
    beta: BetaNoticeSchema = BetaNoticeSchema()

    model_config = ConfigDict(extra="forbid")


class StorageMetricSchema(BaseModel):
    key: str
    label: str
    description: str
    bytes: int = Field(ge=0)
    record_count: int = Field(ge=0)
    included_in_quota: bool
    measurement: str
    tokens: int | None = Field(default=None, ge=0)

    model_config = ConfigDict(extra="forbid")


class StorageDetailsSchema(BaseModel):
    current_plan: CurrentPlanSchema
    usage: StorageUsageSchema
    metrics: list[StorageMetricSchema]
    quota_metering_note: str
    generated_at: str

    model_config = ConfigDict(extra="forbid")


class StorageRetentionPolicySchema(BaseModel):
    mode: Literal["off", "30", "60", "90"]
    days: int = Field(ge=0)
    policy_version: int = Field(ge=1)
    automatic_purge_enabled: bool = False

    model_config = ConfigDict(extra="forbid")


class StorageRetentionUpdateSchema(BaseModel):
    mode: Literal["off", "30", "60", "90"]

    model_config = ConfigDict(extra="forbid")


class StorageRetentionPreviewSchema(BaseModel):
    policy: StorageRetentionPolicySchema
    run_id: str | None
    cutoff: str | None
    candidate_count: int = Field(ge=0)
    candidate_bytes: int = Field(ge=0)
    protected_count: int = Field(ge=0)
    legacy_data_preserved: bool

    model_config = ConfigDict(extra="forbid")


class StorageArchiveSchema(BaseModel):
    item_id: str
    category: str
    source_type: str
    state: Literal["archived", "restored"]
    archived_at: str
    restored_at: str | None = None

    model_config = ConfigDict(extra="forbid")


class StorageReconciliationSchema(BaseModel):
    run_id: str
    status: str
    mismatch_count: int = Field(ge=0)
    category_totals: dict[str, object]
    completed_at: str | None = None

    model_config = ConfigDict(extra="forbid")
