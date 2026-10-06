"""Coordinate actor-scoped numeric menus without copying message bodies."""
from threading import RLock
from services.private_message_policy import as_time, PrivateMessageError

MENU_LOCK = RLock()


def expire_other_menu(db, space, userid, source, now):
    if source == "private":
        table, scope_key, actor_key, actor = (
            "delegation_command_contexts", "owner_user_id", "actor_userid", userid.lower())
    elif source == "delegation":
        people = (db.table("private_message_participants").select("id,wecom_userid")
                  .eq("space_id", space).limit(1000).execute().data)
        matches = [p for p in people if p["wecom_userid"].lower() == userid.lower()]
        if len(matches) != 1:
            return
        table, scope_key, actor_key, actor = (
            "private_message_contexts", "space_id", "actor_id", matches[0]["id"])
    else:
        raise ValueError("Unknown menu source")
    rows = (db.table(table).select("id,version").eq(scope_key, space)
            .eq(actor_key, actor).limit(1).execute().data)
    for row in rows:
        changed = (db.table(table).update({
            "expires_at": now.isoformat(), "updated_at": now.isoformat(),
            "version": row["version"] + 1})
         .eq(scope_key, space).eq(actor_key, actor).eq("id", row["id"])
         .eq("version", row["version"]).execute().data)
        if not changed:
            raise PrivateMessageError("选择菜单正在变化，请重新发起操作")


def delegation_context_active(db, owner, userid, now):
    rows = (db.table("delegation_command_contexts").select("id,expires_at")
            .eq("owner_user_id", owner).eq("actor_userid", userid.lower())
            .limit(1).execute().data)
    return bool(rows and as_time(rows[0]["expires_at"]) > now)
