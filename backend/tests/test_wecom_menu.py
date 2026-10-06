from copy import deepcopy
from datetime import timedelta
import pytest
from private_message_fakes import DB, NOW, SPACE, populate
from services.wecom_menu import expire_other_menu, delegation_context_active


@pytest.fixture
def db():
    db = DB()
    people = populate(db)
    future = (NOW + timedelta(minutes=10)).isoformat()
    db.rows["private_message_contexts"] = [
        {"id": "p-a", "space_id": SPACE, "actor_id": people[1]["id"], "version": 2,
         "expires_at": future, "updated_at": NOW.isoformat()},
        {"id": "p-b", "space_id": SPACE, "actor_id": people[2]["id"], "version": 2,
         "expires_at": future, "updated_at": NOW.isoformat()},
    ]
    db.rows["delegation_command_contexts"] = [
        {"id": "d-a", "owner_user_id": SPACE, "actor_userid": "a", "version": 3,
         "expires_at": future, "updated_at": NOW.isoformat()},
        {"id": "d-b", "owner_user_id": SPACE, "actor_userid": "b", "version": 3,
         "expires_at": future, "updated_at": NOW.isoformat()},
        {"id": "d-elsewhere", "owner_user_id": "other", "actor_userid": "a", "version": 4,
         "expires_at": future, "updated_at": NOW.isoformat()},
    ]
    return db


def test_private_menu_expires_only_same_actor_delegation_context(db):
    expire_other_menu(db, SPACE, "A", "private", NOW)
    rows = db.rows["delegation_command_contexts"]
    assert rows[0]["expires_at"] == NOW.isoformat()
    assert rows[0]["version"] == 4
    assert rows[1]["version"] == 3 and rows[2]["version"] == 4
    assert db.rows["private_message_contexts"][0]["version"] == 2


def test_delegation_menu_expires_only_same_actor_private_context(db):
    expire_other_menu(db, SPACE, "a", "delegation", NOW)
    rows = db.rows["private_message_contexts"]
    assert rows[0]["expires_at"] == NOW.isoformat()
    assert rows[0]["version"] == 3
    assert rows[1]["version"] == 2
    assert db.rows["delegation_command_contexts"][0]["version"] == 3


def test_unknown_actor_cannot_expire_another_private_menu(db):
    before = deepcopy(db.rows["private_message_contexts"])
    expire_other_menu(db, SPACE, "Unknown", "delegation", NOW)
    assert db.rows["private_message_contexts"] == before


def test_context_active_is_scoped_case_insensitive_and_expires(db):
    assert delegation_context_active(db, SPACE, "A", NOW)
    assert not delegation_context_active(db, SPACE, "Unknown", NOW)
    assert not delegation_context_active(db, "missing-space", "A", NOW)
    assert not delegation_context_active(db, SPACE, "A", NOW + timedelta(minutes=10))


def test_expiry_version_change_invalidates_already_read_private_choice(db):
    from services.private_message_service import PrivateMessageService
    service = PrivateMessageService(db, clock=lambda: NOW)
    actor = db.rows["private_message_participants"][1]
    stale = service.context(SPACE, actor)
    expire_other_menu(db, SPACE, "A", "delegation", NOW)
    assert not service.clear_context(SPACE, actor, stale)


def test_unknown_source_is_not_allowed(db):
    with pytest.raises(ValueError):
        expire_other_menu(db, SPACE, "A", "wrong", NOW)

def test_failed_context_invalidation_prevents_new_private_menu(monkeypatch):
    from types import SimpleNamespace
    from services.private_message_policy import PrivateMessageError
    from services.private_message_service import PrivateMessageService
    from private_message_fakes import Query, populate
    db = DB()
    people = populate(db)
    service = PrivateMessageService(db, clock=lambda: NOW)
    db.rows["delegation_command_contexts"] = [{
        "id": "old-task", "owner_user_id": SPACE, "actor_userid": "a", "version": 0,
        "expires_at": (NOW + timedelta(minutes=10)).isoformat(),
    }]
    service.handle(SPACE, people[1], "立即给乙发消息：一")
    service.handle(SPACE, people[1], "立即给丙发消息：二")
    execute = Query.execute
    def race(query):
        if query.name == "delegation_command_contexts" and query.mode == "update":
            return SimpleNamespace(data=[])
        return execute(query)
    monkeypatch.setattr(Query, "execute", race)
    with pytest.raises(PrivateMessageError):
        service.handle(SPACE, people[1], "确认发送")
    assert not db.rows.get("private_message_contexts")
    assert db.rows["delegation_command_contexts"][0]["version"] == 0
