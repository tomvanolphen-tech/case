from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from core.models import InvoiceRecord


class PipelinePhase(str, Enum):
    PENDING  = "pending"
    RUNNING  = "running"
    PROPOSED = "proposed"
    DONE     = "done"
    ERROR    = "error"


@dataclass
class RunState:
    run_id: str
    phase: PipelinePhase = PipelinePhase.PENDING
    record: InvoiceRecord | None = None
    error: str | None = None
    booking_id: str | None = None
    pending_rule: dict[str, Any] | None = None  # rule proposal awaiting confirm_rule


_store: dict[str, RunState] = {}


def create(run_id: str) -> RunState:
    s = RunState(run_id=run_id)
    _store[run_id] = s
    return s


def get(run_id: str) -> RunState | None:
    return _store.get(run_id)


def update(run_id: str, **kwargs) -> None:
    s = _store.get(run_id)
    if s is None:
        return
    for k, v in kwargs.items():
        setattr(s, k, v)


def remove(run_id: str) -> None:
    _store.pop(run_id, None)
