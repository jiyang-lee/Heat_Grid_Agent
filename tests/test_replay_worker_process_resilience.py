from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_replay_worker_isolates_a_bad_run_instead_of_exiting() -> None:
    source = (
        ROOT
        / "simulator"
        / "versions"
        / "v2_postgres_react_ops"
        / "backend"
        / "replay_worker_main.py"
    ).read_text(encoding="utf-8")
    loop = source.split("async def run_forever", maxsplit=1)[1].split(
        "async def _claim_run", maxsplit=1
    )[0]

    assert "except Exception as error:" in loop
    assert "await self._fail_run(str(run[\"run_id\"]), error)" in loop
    assert "async def _fail_run" in source
    assert "state = 'error'" in source
    assert "lease_owner = NULL" in source
