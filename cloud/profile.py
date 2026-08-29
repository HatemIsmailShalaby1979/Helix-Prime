"""Cloud-ready provider facade + synthetic demo profile (Prompt 9).

`CloudProvider` aggregates the eight capability adapters and wraps them with a
guarded call path that enforces (a) restricted-API allow-listing, (b) spend
controls, and (c) safe failure. `DemoController` adds reset and shutdown
procedures for the synthetic cloud-demo profile. Local execution is the default;
cloud adapters are intentionally absent so any non-local request fails safe.
"""
from __future__ import annotations

from typing import Any, Callable, Optional

from .config import CloudConfig, demo_profile
from .errors import SafeFailure
from .interfaces import (
    Database, ObjectStorage, EventTransport, SecretsStore, IdentityProvider,
    Observability, Scheduler, ModelProvider,
)
from .local_adapters import (
    LocalDatabase, LocalObjectStorage, LocalQueue, LocalSecrets, LocalIdentity,
    LocalObservability, LocalScheduler, LocalModel,
)


SPEND_CONTROL_DOCS = """
Spend-control model (synthetic, local-first)
-------------------------------------------
* Every guarded operation may carry a unit cost (default 0.0 in normal use).
* `SpendControl` accumulates estimated spend against `usage_limits.budget_usd`.
* When accumulated spend would exceed the budget, the next guarded call raises
  `SafeFailure` (no silent over-spend, no external billing).
* The cloud-demo profile ships with a tiny synthetic budget (default $0.50) and
  hard usage caps (max_requests, max_records) to keep demos bounded.
* Cloud spend only becomes real when a production config supplies live
  credentials and a non-synthetic, cloud-backed adapter -- which this build does
  NOT do. Budgets are documentation + guardrails until then.

Which cloud services are optional, and when they become justified
---------------------------------------------------------------
All eight capability surfaces are OPTIONAL. Local adapters satisfy them today.
A managed cloud service becomes justified only when local execution hits a
real, measured limit -- see `optional_cloud_services()` for per-service triggers.
"""


def optional_cloud_services() -> list:
    """Document which cloud services are optional and when they become justified."""
    return [
        {"service": "database", "optional": True,
         "justified_when": "durability/multi-tenant scale exceeds the local store; production data retention"},
        {"service": "object_storage", "optional": True,
         "justified_when": "synthetic datasets/artifacts grow beyond local memory or need shared access"},
        {"service": "queue_event_transport", "optional": True,
         "justified_when": "distributed eventing across services / async workloads"},
        {"service": "secrets", "optional": True,
         "justified_when": "real credential management is required (never in a demo profile)"},
        {"service": "identity", "optional": True,
         "justified_when": "SSO / enterprise IdP integration replaces the local identity stub"},
        {"service": "observability", "optional": True,
         "justified_when": "centralized metrics/tracing/log aggregation at scale"},
        {"service": "scheduled_jobs", "optional": True,
         "justified_when": "production cron/orchestration beyond the in-memory scheduler"},
        {"service": "model_providers", "optional": True,
         "justified_when": "production LLM throughput, latency, or cost needs exceed the local stub"},
    ]


class SpendControl:
    def __init__(self, budget: float) -> None:
        self.budget = float(budget)
        self.spent = 0.0

    def charge(self, cost: float) -> float:
        self.spent += float(cost)
        if self.spent > self.budget:
            raise SafeFailure(
                f"spend budget ${self.budget:.4f} exceeded (${self.spent:.4f}); "
                f"operation blocked"
            )
        return self.budget - self.spent

    def remaining(self) -> float:
        return max(0.0, self.budget - self.spent)

    def reset(self) -> None:
        self.spent = 0.0


class DemoController:
    def __init__(self, provider: "CloudProvider", resettable: list) -> None:
        self._provider = provider
        self._resettable = resettable
        self._stopped = False

    def is_stopped(self) -> bool:
        return self._stopped

    def shutdown(self) -> None:
        """Graceful shutdown: further guarded calls are refused."""
        self._stopped = True
        self._provider.observability.log("info", "demo shutdown", action="shutdown")

    def reset(self) -> None:
        """Reset procedure: clears synthetic state, metrics, spend; revives provider."""
        self._stopped = False
        for adapter in self._resettable:
            adapter.reset()
        self._provider.spend.reset()
        self._provider.observability.reset()
        self._provider.observability.log("info", "demo reset", action="reset")


class CloudProvider:
    def __init__(
        self,
        config: CloudConfig,
        db: Database,
        storage: ObjectStorage,
        queue: EventTransport,
        secrets: SecretsStore,
        identity: IdentityProvider,
        observability: Observability,
        scheduler: Scheduler,
        models: ModelProvider,
        spend: SpendControl,
    ) -> None:
        self.config = config
        self.db = db
        self.storage = storage
        self.queue = queue
        self.secrets = secrets
        self.identity = identity
        self.observability = observability
        self.scheduler = scheduler
        self.models = models
        self.spend = spend
        self.controller = DemoController(self, [db, storage, queue, secrets, identity, scheduler, models])

    # ---- guarded entrypoint: restricted API + spend + safe failure ----
    def guarded_call(
        self,
        operation: str,
        cost: float = 0.0,
        func: Optional[Callable[..., Any]] = None,
        *args: Any,
        **kw: Any,
    ) -> Any:
        if self.controller.is_stopped():
            raise SafeFailure("cloud provider is shut down")
        allowed = self.config.allowed_operations
        if operation not in allowed and "*" not in allowed:
            raise SafeFailure(
                f"operation {operation!r} not permitted in restricted demo API"
            )
        self.spend.charge(cost)
        self.observability.record_metric("requests", 1.0, {"operation": operation})
        if func is None:
            return None
        try:
            return func(*args, **kw)
        except SafeFailure:
            raise
        except Exception as exc:  # pragma: no cover - defensive
            self.observability.record_metric("errors", 1.0, {"operation": operation})
            raise SafeFailure(f"operation {operation!r} failed: {exc}") from exc

    def status(self) -> dict:
        snap = self.observability.snapshot()
        return {
            "mode": self.config.mode,
            "synthetic_data_only": self.config.synthetic_data_only,
            "restricted_api": self.config.restricted_api,
            "stopped": self.controller.is_stopped(),
            "spent_usd": self.spend.spent,
            "budget_usd": self.spend.budget,
            "request_count": snap.get("metrics", {}).get("requests", 0),
        }

    # ---- builders ----
    @classmethod
    def build(cls, config: CloudConfig) -> "CloudProvider":
        config.resolve()
        spend = SpendControl(config.usage_limits.budget_usd)
        return cls(
            config=config,
            db=LocalDatabase(),
            storage=LocalObjectStorage(),
            queue=LocalQueue(),
            secrets=LocalSecrets(),
            identity=LocalIdentity(),
            observability=LocalObservability(),
            scheduler=LocalScheduler(),
            models=LocalModel(),
            spend=spend,
        )

    @classmethod
    def local(cls) -> "CloudProvider":
        return cls.build(CloudConfig.from_dict({}))

    @classmethod
    def demo(cls) -> "CloudProvider":
        return cls.build(demo_profile())
