from copy import deepcopy
from uuid import uuid4
from types import SimpleNamespace
from datetime import datetime, timezone


NOW = datetime(2026, 10, 6, 2, 0, tzinfo=timezone.utc)
SPACE = "space"


class Query:
    def __init__(self, db, name):
        self.db, self.name = db, name
        self.filters, self.mode, self.payload = [], "select", None
        self.sort, self.desc, self.cap, self.offset = None, False, 1000, 0
    def select(self, *args): return self
    def eq(self, key, value): self.filters.append((key, "eq", value)); return self
    def is_(self, key, value): self.filters.append((key, "eq", None if value == "null" else value)); return self
    def neq(self, key, value): self.filters.append((key, "neq", value)); return self
    def in_(self, key, values): self.filters.append((key, "in", values)); return self
    def lte(self, key, value): self.filters.append((key, "lte", value)); return self
    def gte(self, key, value): self.filters.append((key, "gte", value)); return self
    def order(self, key, desc=False): self.sort, self.desc = key, desc; return self
    def limit(self, value): self.cap = value; return self
    def range(self, first, last): self.offset, self.cap = first, last - first + 1; return self
    def insert(self, payload): self.mode, self.payload = "insert", payload; return self
    def update(self, payload): self.mode, self.payload = "update", payload; return self
    def delete(self): self.mode = "delete"; return self
    def execute(self):
        self.db.calls.append((self.name, self.mode, deepcopy(self.filters), deepcopy(self.payload)))
        rows = self.db.rows.setdefault(self.name, [])
        if self.mode == "insert":
            payloads = self.payload if isinstance(self.payload, list) else [self.payload]
            for payload in payloads:
                payload.setdefault("id", str(uuid4()))
                payload.setdefault("created_at", NOW.isoformat())
                assert payload.get("space_id") or payload.get("owner_user_id"), "insert needs scope"
                unique = {
                    "private_message_outbox": ("operation_key",),
                    "private_message_contexts": ("space_id", "actor_id"),
                    "private_message_threads": ("space_id", "participant_a", "participant_b"),
                    "private_message_inbound": ("space_id", "msg_id"),
                    "delegation_command_contexts": ("owner_user_id", "actor_userid"),
                    "delegation_outbox": ("owner_user_id", "operation_key"),
                }.get(self.name, ("id",))
                if any(all(r.get(k) == payload.get(k) for k in unique) for r in rows):
                    raise ValueError("duplicate")
                rows.append(deepcopy(payload))
            return SimpleNamespace(data=deepcopy(payloads))
        scope_key = "space_id" if self.name.startswith("private_") else "owner_user_id"
        assert any(k == scope_key and op == "eq" for k, op, _ in self.filters), "scope filter missing"
        def match(row):
            for key, op, value in self.filters:
                actual = row.get(key)
                if op == "eq" and actual != value: return False
                if op == "neq" and actual == value: return False
                if op == "in" and actual not in value: return False
                if op == "lte" and (actual is None or actual > value): return False
                if op == "gte" and (actual is None or actual < value): return False
            return True
        matches = [row for row in rows if match(row)]
        if self.sort:
            matches.sort(key=lambda r: r.get(self.sort) or "", reverse=self.desc)
        matches = matches[self.offset:self.offset + self.cap]
        if self.mode == "update":
            for row in matches: row.update(deepcopy(self.payload))
        if self.mode == "delete":
            for row in matches: rows.remove(row)
        return SimpleNamespace(data=deepcopy(matches))


class DB:
    def __init__(self):
        self.rows, self.calls = {}, []
    def table(self, name): return Query(self, name)


def populate(db):
    people = []
    for name, userid in [("负责人", "Owner"), ("甲", "A"), ("乙", "B"), ("丙", "C")]:
        person = {"id": "person-" + userid, "space_id": SPACE, "wecom_userid": userid,
                  "name": name, "aliases": [], "active": True, "created_at": NOW.isoformat()}
        people.append(person)
    db.rows["private_message_participants"] = people
    return people
