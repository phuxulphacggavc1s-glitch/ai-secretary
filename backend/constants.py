from enum import Enum


class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    WAITING_RESPONSE = "waiting_response"
    BLOCKED = "blocked"
    DONE = "done"
    CANCELLED = "cancelled"


class PriorityLevel(str, Enum):
    S = "S"
    A = "A"
    B = "B"


class EventType(str, Enum):
    CREATED = "created"
    STATUS_CHANGE = "status_change"
    CHECKIN = "checkin"
    AI_PARSE = "ai_parse"
    AI_JUDGE = "ai_judge"
    REMINDER_SENT = "reminder_sent"
    FOLLOW_GENERATED = "follow_generated"


PRIORITY_INT_MAP = {
    PriorityLevel.S.value: 3,
    PriorityLevel.A.value: 2,
    PriorityLevel.B.value: 1,
}

