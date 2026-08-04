from __future__ import annotations

from collections.abc import Awaitable, Callable

from psycopg import AsyncConnection
from psycopg.rows import DictRow


type MigrationConnection = AsyncConnection[DictRow]
type DataHook = Callable[[MigrationConnection], Awaitable[None]]

_HOOKS: dict[int, DataHook] = {}


def register_data_hook(version: int) -> Callable[[DataHook], DataHook]:
    def register(hook: DataHook) -> DataHook:
        _HOOKS[version] = hook
        return hook

    return register


def get_data_hook(version: int) -> DataHook | None:
    return _HOOKS.get(version)
