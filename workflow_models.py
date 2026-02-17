"""
Workflow data models.

Defines the JSON structure for recorded and saved workflows.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field


class WorkflowInputField(BaseModel):
    type: str = "string"
    description: str = ""
    required: bool = False
    default: Optional[str] = None


class WorkflowStep(BaseModel):
    seq: int
    action: str  # e.g. "click", "navigate", "type", "wait_for", etc.
    params: dict[str, Any] = Field(default_factory=dict)
    description: str = ""


class Workflow(BaseModel):
    name: str
    description: str = ""
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    recorded_from: str = ""  # original prompt used for recording
    input_schema: dict[str, WorkflowInputField] = Field(default_factory=dict)
    steps: list[WorkflowStep] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
