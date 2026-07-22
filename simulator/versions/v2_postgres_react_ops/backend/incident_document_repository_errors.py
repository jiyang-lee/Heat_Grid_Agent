from __future__ import annotations


class IncidentDocumentNotFoundError(RuntimeError):
    def __init__(self, resource_id: str) -> None:
        self.resource_id = resource_id
        super().__init__(resource_id)

    def __str__(self) -> str:
        return f"incident document resource not found: {self.resource_id}"


class IncidentDocumentConflictError(RuntimeError):
    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)

    def __str__(self) -> str:
        return self.detail


class InvalidIncidentCitationError(RuntimeError):
    def __init__(self, citation_id: str) -> None:
        self.citation_id = citation_id
        super().__init__(citation_id)

    def __str__(self) -> str:
        return f"unsupported incident citation: {self.citation_id}"
