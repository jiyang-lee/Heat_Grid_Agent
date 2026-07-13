from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from functools import partial
import os
from pathlib import Path
from collections.abc import Iterator

from anyio.to_thread import run_sync

from heatgrid_ops.agent.contracts import ReportWriteRequest
from heatgrid_ops.agent.errors import MissingApiKeyError
from heatgrid_ops.agent.models import JsonValue
from heatgrid_ops.agent.run_models import ReportArtifactDraft
from heatgrid_ops.reports.anomaly import write_anomaly_report_json
from heatgrid_ops.reports.daily import write_daily_report_json


@dataclass(frozen=True, slots=True)
class LocalReportWriterAdapter:
    api_key: str | None
    model: str
    output_root: Path
    mock: bool = False

    async def write_anomaly(
        self,
        request: ReportWriteRequest,
    ) -> ReportArtifactDraft:
        self._require_key()
        path = self._report_path(request.run_id, "anomaly_report.json")
        await run_sync(partial(self._write_anomaly_sync, request, path))
        return ReportArtifactDraft(
            kind="anomaly_report",
            name="anomaly_report.json",
            uri=self._report_uri(request.run_id, "anomaly_report.json"),
        )

    async def write_daily(
        self,
        request: ReportWriteRequest,
    ) -> ReportArtifactDraft:
        self._require_key()
        path = self._report_path(request.run_id, "daily_report.json")
        await run_sync(partial(self._write_daily_sync, request, path))
        return ReportArtifactDraft(
            kind="daily_report",
            name="daily_report.json",
            uri=self._report_uri(request.run_id, "daily_report.json"),
        )

    def _write_anomaly_sync(self, request: ReportWriteRequest, path: Path) -> None:
        with _temporary_report_env(self.api_key, self.model):
            write_anomaly_report_json(
                {
                    "ops_evidence": request.source_input,
                    "external_context": request.evidence_context,
                    "agent_output": request.ops_output.model_dump(mode="json"),
                    "report_context": {
                        "agent_run_id": request.run_id,
                        "source_card_id": request.card_id,
                    },
                },
                path,
                mock=self.mock,
            )

    def _write_daily_sync(self, request: ReportWriteRequest, path: Path) -> None:
        with _temporary_report_env(self.api_key, self.model):
            write_daily_report_json(
                {
                    "report_context": {
                        "agent_run_id": request.run_id,
                        "source_card_id": request.card_id,
                    },
                    "priority_cards": [_priority_card(request.source_input)],
                    "agent_outputs": [request.ops_output.model_dump(mode="json")],
                    "ops_evidence_list": [request.source_input],
                    "external_context_list": [request.evidence_context],
                    "rag_evidence": [],
                    "work_order_summaries": [],
                    "previous_operator_memo": None,
                },
                path,
                mock=self.mock,
            )

    def _require_key(self) -> None:
        if self.api_key is None and not self.mock:
            raise MissingApiKeyError()

    def _report_path(self, run_id: str, filename: str) -> Path:
        return self.output_root / "ops_agent" / "reports" / run_id / filename

    @staticmethod
    def _report_uri(run_id: str, filename: str) -> str:
        return f"output/ops_agent/reports/{run_id}/{filename}"


def default_report_output_root() -> Path:
    return Path(__file__).resolve().parents[4] / "output"


def _priority_card(source_input: dict[str, JsonValue]) -> dict[str, JsonValue]:
    priority_context = source_input.get("priority_context")
    if not isinstance(priority_context, dict):
        return {}
    card = priority_context.get("card")
    return card if isinstance(card, dict) else {}


@contextmanager
def _temporary_report_env(
    api_key: str | None,
    model: str,
) -> Iterator[None]:
    previous_key = os.environ.get("OPENAI_API_KEY")
    previous_model = os.environ.get("OPENAI_MODEL")
    if api_key is not None:
        os.environ["OPENAI_API_KEY"] = api_key
    os.environ["OPENAI_MODEL"] = model
    try:
        yield
    finally:
        _restore_env("OPENAI_API_KEY", previous_key)
        _restore_env("OPENAI_MODEL", previous_model)


def _restore_env(name: str, value: str | None) -> None:
    if value is None:
        os.environ.pop(name, None)
        return
    os.environ[name] = value
