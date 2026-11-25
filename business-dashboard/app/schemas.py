"""Request models.

Pydantic is used only for shape validation; business rules live in
``service``/``config_store`` so they stay testable without HTTP.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


def as_dict(model: BaseModel) -> Dict[str, Any]:
    """exclude_unset across pydantic v1 and v2."""
    if hasattr(model, "model_dump"):
        return model.model_dump(exclude_unset=True)  # type: ignore[attr-defined]
    return model.dict(exclude_unset=True)  # type: ignore[call-arg]


class StateInput(BaseModel):
    customers: List[Dict[str, Any]] = Field(default_factory=list)
    projects: List[Dict[str, Any]] = Field(default_factory=list)
    phases: List[Dict[str, Any]] = Field(default_factory=list)
    orders: List[Dict[str, Any]] = Field(default_factory=list)


class ParseInput(BaseModel):
    text: str = ""
    project_hint: Optional[str] = None


class CaptureInput(BaseModel):
    raw_text: str = ""
    project_id: Optional[str] = None
    parser: str = "local"
    parsed: Dict[str, Any] = Field(default_factory=dict)
    applied: Dict[str, Any] = Field(default_factory=dict)


class CustomerInput(BaseModel):
    name: str = ""
    alias: str = ""
    contact: str = ""
    channel: str = ""


class ProjectPatch(BaseModel):
    name: Optional[str] = None
    model: Optional[str] = None
    customer: Optional[str] = None
    orderId: Optional[str] = None
    round: Optional[int] = None
    phase: Optional[str] = None
    start: Optional[str] = None
    end: Optional[str] = None
    color: Optional[str] = None
    contact: Optional[str] = None
    dept: Optional[str] = None
    deptType: Optional[str] = None
    contactWay: Optional[str] = None
    means: Optional[str] = None
    channel: Optional[str] = None
    note: Optional[str] = None
    next: Optional[str] = None
    updated: Optional[str] = None
    unsure: Optional[List[str]] = None
    done: Optional[List[str]] = None
    milestones: Optional[List[Dict[str, Any]]] = None
    payload: Optional[Dict[str, Any]] = None


class PhasesInput(BaseModel):
    phases: List[Dict[str, Any]] = Field(default_factory=list)


class ProviderInput(BaseModel):
    enabled: Optional[bool] = None
    provider: Optional[str] = None
    base_url: Optional[str] = None
    model: Optional[str] = None
    json_mode: Optional[bool] = None
    api_key: Optional[str] = None


class ImportInput(BaseModel):
    data: Dict[str, Any] = Field(default_factory=dict)
    mode: str = "merge"
