from httpx import ASGITransport, AsyncClient
import pytest

from heat_grid_ops.app import app


@pytest.mark.anyio
async def test_simulation_returns_minimal_output_when_database_is_unavailable() -> None:
    card_id = "10000000-0000-0000-0000-000000000001"
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(f"/api/simulate/{card_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ops_input"]["priority_context"]["card"]["card_id"] == card_id
    assert payload["ops_output"]["summary"]
    assert payload["ops_output"]["action_plan"]
    assert payload["ops_output"]["caution"]
