from __future__ import annotations


def test_open_critical_episode_never_deescalates_on_later_high_anomaly() -> None:
    from simulator.versions.v2_postgres_react_ops.backend.alert_episode_policy import (
        EpisodeSnapshot,
        Observation,
        transition_episode,
    )

    given_open_critical = transition_episode(
        EpisodeSnapshot.empty(),
        Observation.anomaly(severity="critical"),
        anomaly_confirmations=2,
        recovery_confirmations=3,
    )
    when_later_high = transition_episode(
        given_open_critical.snapshot,
        Observation.anomaly(severity="high"),
        anomaly_confirmations=2,
        recovery_confirmations=3,
    )

    assert when_later_high.snapshot.severity == "critical"
    assert when_later_high.action == "unchanged"
    assert when_later_high.opens_alert is False
