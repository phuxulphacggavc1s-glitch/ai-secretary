from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


VALID_TASK_STATUSES = {"pending", "in_progress", "done"}


class TaskCreate(BaseModel):
    raw_input: str = Field(min_length=1, max_length=500)


class TaskConfirm(BaseModel):
    content: str = Field(min_length=1, max_length=500)
    category: str = "其他"
    remind_time: Optional[datetime] = None
    priority: int = Field(default=1, ge=1, le=3)


class TaskUpdate(BaseModel):
    status: Optional[str] = None
    content: Optional[str] = None
    category: Optional[str] = None
    remind_time: Optional[datetime] = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, value):
        if value is not None and value not in VALID_TASK_STATUSES:
            raise ValueError(f"status must be one of {VALID_TASK_STATUSES}")
        return value


class CheckinBody(BaseModel):
    progress_note: Optional[str] = None
    status: Optional[str] = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, value):
        allowed = {"in_progress", "done"}
        if value is not None and value not in allowed:
            raise ValueError(f"status must be one of {allowed}")
        return value
