"""Pydantic schemas for the personal model configuration API."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

ProtocolName = Literal[
    "openai-completions",
    "openai-responses",
    "anthropic-messages",
    "google-generative-ai",
]
ThinkingLevel = Literal["off", "minimal", "low", "medium", "high", "xhigh"]
AuthType = Literal["api_key", "oauth"]
SceneName = Literal[
    "chat_profile",
    "path_outline",
    "course_resources",
    "quiz_vision",
    "growth_report",
    "kb_translate",
    "kb_search",
]

TOOL_SCENES: frozenset[str] = frozenset(
    {"chat_profile", "path_outline", "growth_report"}
)
VISION_SCENES: frozenset[str] = frozenset({"quiz_vision"})
ADMIN_ONLY_SCENES: frozenset[str] = frozenset({"kb_translate", "kb_search"})


class ModelRef(BaseModel):
    provider_id: str = Field(min_length=1, max_length=64)
    model_id: str = Field(min_length=1, max_length=128)


class SlotBinding(BaseModel):
    model_ref: ModelRef
    thinking_level: ThinkingLevel | None = None
    fallback_chain: list[ModelRef] = Field(default_factory=list, max_length=5)


class RuntimeOptions(BaseModel):
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=1, le=1_000_000)
    timeout_seconds: int | None = Field(default=None, ge=1, le=600)
    max_retries: int | None = Field(default=None, ge=0, le=5)
    cache_retention: Literal["none", "short", "long"] | None = None


class ProviderUpsert(BaseModel):
    display_name: str | None = Field(default=None, max_length=128)
    is_builtin: bool = True
    protocol: ProtocolName | None = None
    base_url: str | None = Field(default=None, max_length=512)
    headers: dict[str, str] | None = None
    auth_type: AuthType = "api_key"
    api_key: str | None = Field(default=None, max_length=4096)
    enabled: bool = True


class ProviderView(BaseModel):
    provider_id: str
    display_name: str
    is_builtin: bool
    protocol: str
    base_url: str
    headers: dict[str, str]
    auth_type: AuthType
    has_secret: bool
    secret_mask: str | None
    oauth_status: Literal["authorized", "expired"] | None
    oauth_expires_at: datetime | None
    oauth_account_label: str | None
    enabled: bool
    updated_at: datetime


class CustomModelUpsert(BaseModel):
    provider_id: str = Field(min_length=1, max_length=64)
    model_id: str = Field(min_length=1, max_length=128)
    display_name: str | None = Field(default=None, max_length=128)
    context_window: int = Field(default=128000, ge=1)
    max_tokens: int = Field(default=8192, ge=1)
    supports_vision: bool = False
    supports_tools: bool = True
    supports_reasoning: bool = False
    compat_config: dict = Field(default_factory=dict)
    pricing: dict = Field(default_factory=dict)
    enabled: bool = True


class CustomModelView(BaseModel):
    id: str
    provider_id: str
    model_id: str
    display_name: str
    context_window: int
    max_tokens: int
    supports_vision: bool
    supports_tools: bool
    supports_reasoning: bool
    compat_config: dict
    pricing: dict
    enabled: bool
    updated_at: datetime


class PreferencesPayload(BaseModel):
    config_mode: Literal["simple", "advanced"] = "simple"
    default_model_ref: ModelRef | None = None
    default_vision_model_ref: ModelRef | None = None
    default_thinking_level: ThinkingLevel = "medium"
    runtime_options: RuntimeOptions = Field(default_factory=RuntimeOptions)
    slot_bindings: dict[SceneName, SlotBinding] = Field(default_factory=dict)


class PreferencesView(PreferencesPayload):
    updated_at: datetime | None = None


class QuickSwitchPayload(BaseModel):
    model_ref: ModelRef | None = None
    thinking_level: ThinkingLevel | None = None


class ModelConfigView(BaseModel):
    providers: list[ProviderView]
    custom_models: list[CustomModelView]
    preferences: PreferencesView


class UsageBucket(BaseModel):
    date: str
    scene: str
    requests: int
    success_requests: int
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    reasoning_tokens: int
    estimated_cost_usd: float
    avg_latency_ms: float


class UsageSummary(BaseModel):
    days: int
    buckets: list[UsageBucket]
    total_requests: int
    total_tokens: int
    total_cost_usd: float


class UsageRecordPayload(BaseModel):
    request_id: str | None = Field(default=None, max_length=128)
    scene: str = Field(min_length=1, max_length=64)
    provider_id: str = Field(min_length=1, max_length=64)
    model_id: str = Field(min_length=1, max_length=128)
    thinking_level: str | None = Field(default=None, max_length=16)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    cache_read_tokens: int = Field(default=0, ge=0)
    cache_write_tokens: int = Field(default=0, ge=0)
    reasoning_tokens: int = Field(default=0, ge=0)
    estimated_cost_usd: float = Field(default=0.0, ge=0)
    latency_ms: int = Field(default=0, ge=0)
    success: bool = True
    error_code: str | None = Field(default=None, max_length=64)


class OAuthCredentialPayload(BaseModel):
    credential: dict
    expires_at: datetime | None = None
    account_label: str | None = Field(default=None, max_length=128)


class OAuthRefreshPayload(BaseModel):
    previous_refresh_fingerprint: str | None = None
    new_credential: dict | None = None
    expires_at: datetime | None = None
