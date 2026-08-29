"""Provider-neutral cloud interfaces (Prompt 9).

These abstract the eight capability surfaces Helix Codex may eventually delegate
to external providers. Local adapters implement them today; a future cloud
adapter need only satisfy the same contract. No interface imports a network
library — they are pure capability signatures, so the system stays local-first.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable, Optional


class Database(ABC):
    @abstractmethod
    def put(self, namespace: str, key: str, value: Any) -> None: ...

    @abstractmethod
    def get(self, namespace: str, key: str) -> Optional[Any]: ...

    @abstractmethod
    def delete(self, namespace: str, key: str) -> None: ...

    @abstractmethod
    def query(self, namespace: str, prefix: str = "") -> dict: ...

    def reset(self) -> None:  # local adapters override; interface provides hook
        pass


class ObjectStorage(ABC):
    @abstractmethod
    def put_object(self, bucket: str, key: str, data: bytes) -> None: ...

    @abstractmethod
    def get_object(self, bucket: str, key: str) -> bytes: ...

    @abstractmethod
    def delete_object(self, bucket: str, key: str) -> None: ...

    @abstractmethod
    def list_objects(self, bucket: str, prefix: str = "") -> list: ...

    def reset(self) -> None:
        pass


class EventTransport(ABC):
    @abstractmethod
    def publish(self, topic: str, message: dict) -> None: ...

    @abstractmethod
    def subscribe(self, topic: str, handler: Callable[[dict], None]) -> None: ...

    def reset(self) -> None:
        pass


class SecretsStore(ABC):
    @abstractmethod
    def get_secret(self, name: str) -> Optional[str]: ...

    @abstractmethod
    def set_secret(self, name: str, value: str) -> None: ...

    def reset(self) -> None:
        pass


class IdentityProvider(ABC):
    @abstractmethod
    def register(self, user_id: str, token: str, roles: list) -> None: ...

    @abstractmethod
    def authenticate(self, token: str) -> Optional[str]: ...

    @abstractmethod
    def authorize(self, user_id: str, role: str) -> bool: ...

    def reset(self) -> None:
        pass


class Observability(ABC):
    @abstractmethod
    def record_metric(self, name: str, value: float, tags: Optional[dict] = None) -> None: ...

    @abstractmethod
    def log(self, level: str, message: str, **kw: Any) -> None: ...

    @abstractmethod
    def snapshot(self) -> dict: ...

    def reset(self) -> None:
        pass


class Scheduler(ABC):
    @abstractmethod
    def schedule(self, job_id: str, due_at: str, payload: dict) -> None: ...

    @abstractmethod
    def run_due(self, as_of: str) -> list: ...

    def reset(self) -> None:
        pass


class ModelProvider(ABC):
    @abstractmethod
    def complete(self, prompt: str, **kw: Any) -> str: ...

    def reset(self) -> None:
        pass
