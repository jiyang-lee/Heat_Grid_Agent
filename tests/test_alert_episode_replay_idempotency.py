from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_open_alert_is_idempotent_when_replay_reuses_alert_id() -> None:
    source = (
        ROOT
        / "simulator"
        / "versions"
        / "v2_postgres_react_ops"
        / "backend"
        / "alert_episode_repository.py"
    ).read_text(encoding="utf-8")
    open_alert = source.split("async def _open_alert", maxsplit=1)[1].split(
        "async def _update_open_alert", maxsplit=1
    )[0]

    assert "ON CONFLICT (alert_id) DO UPDATE SET" in open_alert
    assert "evaluation_run_id = EXCLUDED.evaluation_run_id" in open_alert
    assert "episode_id = EXCLUDED.episode_id" in open_alert
