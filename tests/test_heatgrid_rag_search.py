from typing import Any

from heatgrid_rag.pgstore import PgVectorStore


class FakeCursor:
    def __init__(self) -> None:
        self.query_count = 0

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, *args: Any) -> None:
        return None

    def execute(self, query: str) -> None:
        self.query_count += 1

    def fetchone(self) -> tuple[int] | tuple[None, None]:
        if self.query_count == 1:
            return (1,)
        return (None, None)


class FakeConnection:
    def __enter__(self) -> "FakeConnection":
        return self

    def __exit__(self, *args: Any) -> None:
        return None

    def cursor(self) -> FakeCursor:
        return FakeCursor()


class FakePsycopg:
    def connect(self, database_url: str, connect_timeout: int) -> FakeConnection:
        return FakeConnection()


def test_pgvector_store_is_unavailable_when_required_tables_are_missing() -> None:
    store = PgVectorStore(database_url="postgresql://example")
    store._psycopg = FakePsycopg()

    assert store.available is False
