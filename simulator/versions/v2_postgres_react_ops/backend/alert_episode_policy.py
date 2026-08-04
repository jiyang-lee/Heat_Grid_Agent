from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, assert_never

EpisodeStatus = Literal["none", "pending", "open", "resolved"]
Severity = Literal["high", "critical"]
ObservationKind = Literal["anomaly", "normal", "freeze"]
TransitionAction = Literal["pending", "opened", "resolved", "escalated", "unchanged", "frozen"]


class EpisodeInvariantError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class Observation:
    kind: ObservationKind
    severity: Severity | None = None

    @classmethod
    def anomaly(cls, *, severity: Severity) -> Observation:
        return cls(kind="anomaly", severity=severity)

    @classmethod
    def normal(cls) -> Observation:
        return cls(kind="normal")

    @classmethod
    def freeze(cls) -> Observation:
        return cls(kind="freeze")


@dataclass(frozen=True, slots=True)
class EpisodeSnapshot:
    status: EpisodeStatus
    severity: Severity | None
    anomaly_count: int
    normal_count: int

    @classmethod
    def empty(cls) -> EpisodeSnapshot:
        return cls(status="none", severity=None, anomaly_count=0, normal_count=0)


@dataclass(frozen=True, slots=True)
class EpisodeTransition:
    snapshot: EpisodeSnapshot
    action: TransitionAction
    opens_alert: bool

    @property
    def status(self) -> EpisodeStatus:
        return self.snapshot.status

    @property
    def anomaly_count(self) -> int:
        return self.snapshot.anomaly_count


@dataclass(frozen=True, slots=True)
class EpisodePolicy:
    anomaly_confirmations: int
    recovery_confirmations: int


def transition_episode(
    snapshot: EpisodeSnapshot,
    observation: Observation,
    *,
    anomaly_confirmations: int,
    recovery_confirmations: int,
) -> EpisodeTransition:
    match observation.kind:
        case "freeze":
            return EpisodeTransition(snapshot=snapshot, action="frozen", opens_alert=False)
        case "normal":
            return _normal_transition(snapshot, recovery_confirmations)
        case "anomaly":
            if observation.severity is None:
                raise EpisodeInvariantError("anomaly observation requires severity")
            return _anomaly_transition(snapshot, observation.severity, anomaly_confirmations)
        case unreachable:
            assert_never(unreachable)


def _normal_transition(snapshot: EpisodeSnapshot, recovery_confirmations: int) -> EpisodeTransition:
    next_normal = snapshot.normal_count + 1
    if snapshot.status in {"open", "pending"} and next_normal >= recovery_confirmations:
        return EpisodeTransition(
            snapshot=EpisodeSnapshot("resolved", snapshot.severity, 0, next_normal),
            action="resolved",
            opens_alert=False,
        )
    return EpisodeTransition(
        snapshot=EpisodeSnapshot(snapshot.status, snapshot.severity, 0, next_normal),
        action="unchanged",
        opens_alert=False,
    )


def _anomaly_transition(
    snapshot: EpisodeSnapshot,
    severity: Severity,
    anomaly_confirmations: int,
) -> EpisodeTransition:
    next_count = snapshot.anomaly_count + 1
    if severity == "critical" or next_count >= anomaly_confirmations:
        effective_severity: Severity = (
            "critical" if snapshot.severity == "critical" else severity
        )
        action: TransitionAction = "opened" if snapshot.status != "open" else "unchanged"
        if snapshot.status == "open" and snapshot.severity == "high" and severity == "critical":
            action = "escalated"
        return EpisodeTransition(
            snapshot=EpisodeSnapshot("open", effective_severity, next_count, 0),
            action=action,
            opens_alert=snapshot.status != "open",
        )
    return EpisodeTransition(
        snapshot=EpisodeSnapshot("pending", severity, next_count, 0),
        action="pending",
        opens_alert=False,
    )
