from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from constants import PriorityLevel, TaskStatus


VALID_TASK_STATUSES = {status.value for status in TaskStatus}
CHECKIN_ALLOWED_STATUSES = {
    TaskStatus.IN_PROGRESS.value,
    TaskStatus.WAITING_RESPONSE.value,
    TaskStatus.BLOCKED.value,
    TaskStatus.DONE.value,
}


class TaskCreate(BaseModel):
    raw_input: str = Field(min_length=1, max_length=500)


class TaskConfirm(BaseModel):
    content: str = Field(min_length=1, max_length=500)
    category: str = "其他"
    remind_time: Optional[datetime] = None
    priority: int = Field(default=1, ge=1, le=3)
    next_action: Optional[str] = Field(default=None, max_length=500)
    next_follow_time: Optional[datetime] = None
    priority_level: PriorityLevel = PriorityLevel.B


class TaskUpdate(BaseModel):
    status: Optional[str] = None
    content: Optional[str] = None
    category: Optional[str] = None
    remind_time: Optional[datetime] = None
    next_action: Optional[str] = Field(default=None, max_length=500)
    next_follow_time: Optional[datetime] = None
    priority_level: Optional[PriorityLevel] = None

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
        if value is not None and value not in CHECKIN_ALLOWED_STATUSES:
            raise ValueError(f"status must be one of {CHECKIN_ALLOWED_STATUSES}")
        return value


class ReplyBody(BaseModel):
    reply_text: str = Field(min_length=1, max_length=1000)


class ChatBody(BaseModel):
    message: str = Field(min_length=1, max_length=500)
