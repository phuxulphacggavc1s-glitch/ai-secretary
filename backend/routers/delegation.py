"""负责人专属同事目录和委派任务接口。"""
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import AwareDatetime, BaseModel, Field
from auth import get_current_user
from services import delegation_entry
from services.delegation import DelegationError
from services.delegation_parser import parse_delegation

router = APIRouter(prefix="/delegation", tags=["delegation"])

class ColleagueCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    wecom_userid: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_@.\-]+$")
    aliases: list[str] = Field(default_factory=list, max_length=20)

class ColleagueUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    aliases: list[str] | None = Field(default=None, max_length=20)
    active: bool | None = None

class TaskCreate(BaseModel):
    colleague_id: str
    content: str = Field(min_length=1, max_length=1000)
    scheduled_at: AwareDatetime
    due_at: AwareDatetime | None = None

class Action(BaseModel):
    action: Literal["approve", "cancel", "modify", "complete", "reopen"]
    content: str | None = Field(default=None, max_length=1000)

class Parse(BaseModel):
    raw_input: str = Field(min_length=1, max_length=1000)

def run(operation):
    try:
        return operation(delegation_entry.get_service())
    except DelegationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        raise HTTPException(status_code=503, detail="委派服务暂不可用，请确认数据库已升级")

@router.get("/settings")
def settings(user=Depends(get_current_user)):
    return {"enabled": delegation_entry.WECOM_DELEGATION_ENABLED}

@router.get("/colleagues")
def colleagues(user=Depends(get_current_user)):
    return {"colleagues":run(lambda service: service.list_colleagues(user.id))}

@router.post("/colleagues")
def add_colleague(body: ColleagueCreate, user=Depends(get_current_user)):
    return {"colleague":run(lambda service: service.save_colleague(user.id, body.model_dump()))}

@router.patch("/colleagues/{colleague_id}")
def edit_colleague(colleague_id: str, body: ColleagueUpdate, user=Depends(get_current_user)):
    return {"colleague":run(lambda service: service.save_colleague(user.id, body.model_dump(exclude_none=True), colleague_id))}

@router.get("/tasks")
def tasks(user=Depends(get_current_user)):
    return {"tasks":run(lambda service: service.list_tasks(user.id))}

@router.post("/tasks")
def create(body: TaskCreate, user=Depends(get_current_user)):
    return {"task":run(lambda service: service.create_task(user.id, body.model_dump()))}

@router.post("/parse")
def parse(body: Parse, user=Depends(get_current_user)):
    return {"parsed":run(lambda service: parse_delegation(body.raw_input, service.list_colleagues(user.id)))}

@router.post("/tasks/{task_id}/action")
def action(task_id: str, body: Action, user=Depends(get_current_user)):
    if body.action == "approve" and not delegation_entry.WECOM_DELEGATION_ENABLED:
        raise HTTPException(status_code=409, detail="委派发送尚未启用")
    return {"task":run(lambda service: service.action(user.id, task_id, body.action, body.content))}

@router.get("/tasks/{task_id}/events")
def events(task_id: str, user=Depends(get_current_user)):
    return {"events":run(lambda service: service.events(user.id, task_id))}
