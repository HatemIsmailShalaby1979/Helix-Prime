"""
Engine port — the boundary the control plane programs against.

Why this module exists
----------------------
There used to be two adapter generations: C4 (``engines/registry.py`` +
``engines/contracts.py``, tracked and covered by ``test_c4_engines.py``) and C5
(``engines/base_adapter.py`` + ``engines/adapters.py``, imported only by
``control_plane/control_seam.py`` and covered by nothing). Two generations of
the same idea is how a codebase stops being reviewable: every new engine had to
ask which generation it was supposed to implement.

Phase 1 W2 retires C5. Four ideas survived the excision and were folded into
the C4 contract (``engines/contracts.py``): the immutable request payload
(``FrozenMapping``), ``ComputationEvidence``, per-engine baselines declared as
data (``ENGINE_BASELINE_PAYLOADS``), and ``EngineResult.refusal``.

What is left is the shape of the boundary itself, and that belongs to the
control plane rather than to the engines: the control plane is the caller, so it
states what it needs. Engines satisfy it however they like — the C4 adapters
satisfy it through ``C4AdapterBridge`` in ``engines/registry.py``.

The port is deliberately small. A port that grows a helper method per engine
eventually becomes a second engine.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Protocol, runtime_checkable

from contracts.task import TaskRequest, TaskResult
from engines.contracts import ComputationEvidence, EngineResult

__all__ = ["EngineInvocation", "EnginePort"]


@dataclass
class EngineInvocation:
    """
    Everything the control plane needs from one engine call.

    Three views of the same computation, kept apart on purpose:

    * ``task_result``   — the canonical control-plane contract object.
    * ``engine_result`` — the engine's own typed envelope, including metrics.
    * ``computation_evidence`` — how the numbers were produced.

    Collapsing them into one dict is what made the old cockpit able to show a
    number without showing its provenance.
    """

    task_result: TaskResult
    engine_result: EngineResult
    computation_evidence: ComputationEvidence

    @property
    def status(self) -> str:
        return self.task_result.status

    @property
    def metrics(self) -> Dict[str, Any]:
        return self.engine_result.metrics

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_result": self.task_result.to_dict(),
            "engine_result": self.engine_result.to_dict(),
            "computation_evidence": self.computation_evidence.to_dict(),
        }


@runtime_checkable
class EnginePort(Protocol):
    """
    The minimum an engine must satisfy to be invoked by the control plane.

    ``execute`` never raises across the boundary: a refusal, a policy denial and
    a crashed computation all come back as an :class:`EngineInvocation` whose
    ``task_result.status`` says which happened. That is what lets the seam
    record a typed outcome instead of unwinding a stack.
    """

    engine_id: str

    def execute(self, request: TaskRequest, *, sample_data_mode: bool = False) -> EngineInvocation:
        ...  # pragma: no cover - protocol
