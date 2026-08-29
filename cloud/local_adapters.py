"""Local, in-memory adapters for the cloud interfaces (Prompt 9).

Every adapter is deterministic and offline: no sockets, no cloud SDKs, no
wall-clock dependence. They are the default backing for local-first execution
and for the synthetic cloud-demo profile (which is local underneath).
"""
from __future__ import annotations

from typing import Any, Callable, Optional

from .interfaces import (
    Database, ObjectStorage, EventTransport, SecretsStore, IdentityProvider,
    Observability, Scheduler, ModelProvider,
)


class LocalDatabase(Database):
    def __init__(self) -> None:
        self._data: dict = {}

    def put(self, namespace: str, key: str, value: Any) -> None:
        self._data.setdefault(namespace, {})[key] = value

    def get(self, namespace: str, key: str) -> Optional[Any]:
        return self._data.get(namespace, {}).get(key)

    def delete(self, namespace: str, key: str) -> None:
        self._data.get(namespace, {}).pop(key, None)

    def query(self, namespace: str, prefix: str = "") -> dict:
        ns = self._data.get(namespace, {})
        if not prefix:
            return dict(ns)
        return {k: v for k, v in ns.items() if k.startswith(prefix)}

    def reset(self) -> None:
        self._data.clear()


class LocalObjectStorage(ObjectStorage):
    def __init__(self) -> None:
        self._store: dict = {}

    def put_object(self, bucket: str, key: str, data: bytes) -> None:
        self._store[(bucket, key)] = bytes(data)

    def get_object(self, bucket: str, key: str) -> bytes:
        if (bucket, key) not in self._store:
            raise KeyError(f"object {bucket}/{key} not found")
        return self._store[(bucket, key)]

    def delete_object(self, bucket: str, key: str) -> None:
        self._store.pop((bucket, key), None)

    def list_objects(self, bucket: str, prefix: str = "") -> list:
        return [k for (b, k) in self._store if b == bucket and k.startswith(prefix)]

    def reset(self) -> None:
        self._store.clear()


class LocalQueue(EventTransport):
    def __init__(self) -> None:
        self._handlers: dict = {}
        self._messages: dict = {}

    def publish(self, topic: str, message: dict) -> None:
        self._messages.setdefault(topic, []).append(message)
        for h in self._handlers.get(topic, []):
            h(message)

    def subscribe(self, topic: str, handler: Callable[[dict], None]) -> None:
        self._handlers.setdefault(topic, []).append(handler)

    def reset(self) -> None:
        self._handlers.clear()
        self._messages.clear()


class LocalSecrets(SecretsStore):
    def __init__(self) -> None:
        self._secrets: dict = {}

    def get_secret(self, name: str) -> Optional[str]:
        return self._secrets.get(name)

    def set_secret(self, name: str, value: str) -> None:
        self._secrets[name] = value

    def reset(self) -> None:
        self._secrets.clear()


class LocalIdentity(IdentityProvider):
    def __init__(self) -> None:
        self._users: dict = {}   # token -> {user_id, roles}

    def register(self, user_id: str, token: str, roles: list) -> None:
        self._users[token] = {"user_id": user_id, "roles": list(roles)}

    def authenticate(self, token: str) -> Optional[str]:
        rec = self._users.get(token)
        return rec["user_id"] if rec else None

    def authorize(self, user_id: str, role: str) -> bool:
        for rec in self._users.values():
            if rec["user_id"] == user_id and role in rec["roles"]:
                return True
        return False

    def reset(self) -> None:
        self._users.clear()


class LocalObservability(Observability):
    def __init__(self) -> None:
        self._metrics: dict = {}
        self._logs: list = []

    def record_metric(self, name: str, value: float, tags: Optional[dict] = None) -> None:
        self._metrics[name] = self._metrics.get(name, 0.0) + float(value)

    def log(self, level: str, message: str, **kw: Any) -> None:
        self._logs.append({"level": level, "message": message, **kw})

    def snapshot(self) -> dict:
        return {"metrics": dict(self._metrics), "log_count": len(self._logs)}

    def reset(self) -> None:
        self._metrics.clear()
        self._logs.clear()


class LocalScheduler(Scheduler):
    def __init__(self) -> None:
        self._jobs: dict = {}

    def schedule(self, job_id: str, due_at: str, payload: dict) -> None:
        self._jobs[job_id] = {"due_at": due_at, "payload": dict(payload), "status": "pending"}

    def run_due(self, as_of: str) -> list:
        done = []
        for job_id, job in self._jobs.items():
            if job["status"] == "pending" and job["due_at"] <= as_of:
                job["status"] = "done"
                done.append((job_id, job["payload"]))
        return done

    def reset(self) -> None:
        self._jobs.clear()


class LocalModel(ModelProvider):
    def complete(self, prompt: str, **kw: Any) -> str:
        # Deterministic local stand-in; never calls an external LLM.
        return f"[local-model] {prompt[:64]}"
