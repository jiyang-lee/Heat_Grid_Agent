from __future__ import annotations


class StaleOperationsReportVersionError(RuntimeError):
    def __str__(self) -> str:
        return "operations report version is stale"
