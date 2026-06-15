import pytest
from pydantic import ValidationError

from models.schemas import ReplyBody, TaskConfirm, TaskCreate, TaskUpdate


def test_task_create_rejects_raw_input_over_500_chars():
    with pytest.raises(ValidationError):
        TaskCreate(raw_input="a" * 501)


def test_task_confirm_rejects_content_over_500_chars():
    with pytest.raises(ValidationError):
        TaskConfirm(content="a" * 501)


def test_task_update_rejects_unknown_status():
    with pytest.raises(ValidationError):
        TaskUpdate(status="unknown")


def test_reply_body_requires_content():
    with pytest.raises(ValidationError):
        ReplyBody(reply_text="")
