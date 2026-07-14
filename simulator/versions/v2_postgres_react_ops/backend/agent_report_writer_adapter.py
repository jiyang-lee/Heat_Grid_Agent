from __future__ import annotations

from dataclasses import dataclass
from functools import partial
from pathlib import Path

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
        path = self._report_path(
            request.run_id,
            "anomaly_report.json",
            request.source_output_hash,
        )
        await run_sync(partial(self._write_anomaly_sync, request, path))
        return ReportArtifactDraft(
            kind="anomaly_report",
            name="anomaly_report.json",
            uri=self._report_uri(
                request.run_id,
                "anomaly_report.json",
                request.source_output_hash,
            ),
        )

    async def write_daily(
        self,
        request: ReportWriteRequest,
    ) -> ReportArtifactDraft:
        self._require_key()
        path = self._report_path(
            request.run_id,
            "daily_report.json",
            request.source_output_hash,
        )
        await run_sync(partial(self._write_daily_sync, request, path))
        return ReportArtifactDraft(
            kind="daily_report",
            name="daily_report.json",
            uri=self._report_uri(
                request.run_id,
                "daily_report.json",
                request.source_output_hash,
            ),
        )

    def _write_anomaly_sync(self, request: ReportWriteRequest, path: Path) -> None:
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
            api_key=self.api_key,
            model=self.model,
        )

    def _write_daily_sync(self, request: ReportWriteRequest, path: Path) -> None:
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
            api_key=self.api_key,
            model=self.model,
        )

    def _require_key(self) -> None:
        if self.api_key is None and not self.mock:
            raise MissingApiKeyError()

    def _report_path(
        self,
        run_id: str,
        filename: str,
        source_output_hash: str | None = None,
    ) -> Path:
        root = self.output_root / "ops_agent" / "reports" / run_id
        return root / filename if source_output_hash is None else root / source_output_hash / filename

    @staticmethod
    def _report_uri(
        run_id: str,
        filename: str,
        source_output_hash: str | None = None,
    ) -> str:
        version = "" if source_output_hash is None else f"{source_output_hash}/"
        return f"output/ops_agent/reports/{run_id}/{version}{filename}"


def default_report_output_root() -> Path:
    return Path(__file__).resolve().parents[4] / "output"


def _priority_card(source_input: dict[str, JsonValue]) -> dict[str, JsonValue]:
    priority_context = source_input.get("priority_context")
    if not isinstance(priority_context, dict):
        return {}
    card = priority_context.get("card")
    return card if isinstance(card, dict) else {}
