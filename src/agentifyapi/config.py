"""YAML configuration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class ServiceConfig(BaseModel):
    name: str
    owner: str | None = None
    # FastAPI-native: "package.module:app" (imported and introspected)
    app: str | None = None
    app_dir: str | None = None  # repo path to put on sys.path when importing `app`
    # HTTP: base URL of the running service. openapi_url defaults to base_url + /openapi.json
    base_url: str | None = None
    openapi_url: str | None = None
    # extension point: protobuf/gRPC descriptors (not implemented in v1)
    proto: str | None = None


class CallerConfig(BaseModel):
    name: str
    roles: list[str] = Field(default_factory=list)


class PolicyRule(BaseModel):
    tools: list[str] = Field(default_factory=lambda: ["*"])  # fnmatch patterns on tool names
    roles: list[str] = Field(default_factory=list)
    callers: list[str] = Field(default_factory=list)


class PolicyConfig(BaseModel):
    allow_anonymous: bool = False  # dev mode: unauthenticated callers may call any enabled tool
    api_keys: dict[str, CallerConfig] = Field(default_factory=dict)
    rules: list[PolicyRule] = Field(default_factory=list)


class Settings(BaseModel):
    database: str = "registry.db"
    audit_log: str = "audit.log"
    crawl_interval_seconds: int = 0  # 0 = only on demand
    redact_pii: bool = True
    services: list[ServiceConfig] = Field(default_factory=list)
    policy: PolicyConfig = Field(default_factory=PolicyConfig)


def load_settings(path: str | Path | None) -> Settings:
    if not path:
        return Settings()
    data: dict[str, Any] = yaml.safe_load(Path(path).read_text()) or {}
    return Settings.model_validate(data)
