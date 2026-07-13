from __future__ import annotations

import asyncio


def selector_event_loop_factory() -> asyncio.AbstractEventLoop:
    return asyncio.SelectorEventLoop()
