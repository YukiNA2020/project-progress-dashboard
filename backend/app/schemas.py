"""Pydantic request models."""

from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field, validator


class ProjectInput(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    folder_path: str = Field(..., min_length=1, max_length=2000)
    planned_start: date
    planned_end: date

    @validator("name", "folder_path")
    def strip_required(cls, value: str) -> str:
        result = value.strip()
        if not result:
            raise ValueError("不能为空")
        return result

    @validator("planned_end")
    def valid_range(cls, value: date, values: dict) -> date:
        start = values.get("planned_start")
        if start and value < start:
            raise ValueError("计划结束日期不能早于计划开始日期")
        return value


class DecisionInput(BaseModel):
    decision: str = Field(..., description="accept 或 dismiss")

    @validator("decision")
    def known_decision(cls, value: str) -> str:
        if value not in ("accept", "dismiss"):
            raise ValueError("decision 只能是 accept 或 dismiss")
        return value


class ProviderInput(BaseModel):
    """Provider configuration.

    ``api_key`` is never echoed back. Omit it to keep the stored key; send an
    empty string to remove it.
    """

    enabled: Optional[bool] = None
    provider: Optional[str] = Field(default=None, max_length=40)
    base_url: Optional[str] = Field(default=None, max_length=500)
    model: Optional[str] = Field(default=None, max_length=120)
    json_mode: Optional[bool] = None
    api_key: Optional[str] = Field(default=None, max_length=400)

    @validator("provider", "base_url", "model", "api_key")
    def strip_optional(cls, value: Optional[str]) -> Optional[str]:
        return value.strip() if isinstance(value, str) else value
