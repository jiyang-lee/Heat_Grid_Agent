from __future__ import annotations

import argparse
import asyncio
import os
import sys

import anyio

from heatgrid_ops.db.migrations import (
    migrate_database,
    provision_application_role,
    verify_database_contract,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="heatgrid-db-migrate")
    parser.add_argument("command", choices=("migrate", "verify", "provision-role"))
    parser.add_argument(
        "--database-url",
        default=os.getenv("HEATGRID_MIGRATION_DATABASE_URL")
        or os.getenv("HEATGRID_DATABASE_URL")
        or os.getenv("DATABASE_URL"),
    )
    return parser


async def _run(args: argparse.Namespace) -> None:
    database_url = args.database_url
    if not database_url:
        raise SystemExit("a migration database URL is required")
    if args.command == "migrate":
        await migrate_database(database_url)
    elif args.command == "verify":
        await verify_database_contract(database_url)
    else:
        password = os.getenv("HEATGRID_APP_PASSWORD")
        if not password:
            raise SystemExit("HEATGRID_APP_PASSWORD is required")
        await provision_application_role(
            database_url,
            app_role=os.getenv("HEATGRID_APP_ROLE", "heatgrid_app"),
            app_password=password,
        )


def main() -> None:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    anyio.run(_run, _parser().parse_args())
