from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class TaskCreate(BaseModel):
    raw_input: str = Field(min_length=1)


class TaskConfirm(BaseModel):
    content: str = Field(min_length=1)
    category: str = "其他"
    remind_time: Optional[datetime] = None
    priority: int = Field(default=1, ge=1, le=3)


class TaskUpdate(BaseModel):
    status: Optional[str] = None
    content: Optional[str] = None
    category: Optional[str] = None
    remind_time: Optional[datetime] = None


class ParsedTask(BaseModel):
    content: str
    category: str
    remind_time: Optional[str] = None
    is_time_clear: bool
    original_time_text: Optional[str] = None
