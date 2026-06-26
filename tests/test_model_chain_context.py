from __future__ import annotations

import pandas as pd

from agent.model_chain.run_model_chain import _context_frame


def test_context_frame_normalizes_manufacturer_and_merges_labels_with_heterogeneous_timestamps():
    preprocessed = pd.DataFrame(
        [
            {
                "substation_id": 1,
                "window_start": "2026-06-25 00:00:00",
                "window_end": "2026-06-25 06:00:00",
                "source_file": "manufacturer_1/operational_data/substation_1.csv",
                "configuration_type": "sh_dhw",
                "has_dhw": 1,
                "has_buffer_tank": 0,
                "days_since_last_fault_event": 1.5,
                "days_since_last_task_event": 2.5,
                "days_since_last_any_event": 3.5,
            }
        ]
    )

    labels = pd.DataFrame(
        [
            {
                "manufacturer": "manufacturer 1",
                "substation_id": 1,
                "window_start": "2026-06-25T00:00:00+00:00",
                "window_end": "2026-06-25T06:00:00+00:00",
                "label": "pre_fault",
                "lead_time_bucket": "1-3d",
                "estimated_lead_time_hours": 36.0,
            }
        ]
    )

    out = _context_frame(preprocessed, labels)
    assert out.loc[0, "manufacturer"] == "manufacturer 1"
    assert out.loc[0, "label"] == "pre_fault"
    assert out.loc[0, "lead_time_bucket"] == "1-3d"
    assert out.loc[0, "estimated_lead_time_hours"] == 36.0


def test_context_frame_keeps_rows_without_matching_labels_when_timestamps_invalid():
    preprocessed = pd.DataFrame(
        [
            {
                "substation_id": 1,
                "window_start": "bad-timestamp",
                "window_end": "2026-06-25 06:00:00",
                "source_file": "manufacturer 2/operational_data/substation_2.csv",
                "configuration_type": "sh",
                "has_dhw": 0,
                "has_buffer_tank": 0,
                "days_since_last_fault_event": 1.5,
                "days_since_last_task_event": 2.5,
                "days_since_last_any_event": 3.5,
            }
        ]
    )
    labels = pd.DataFrame(
        [
            {
                "manufacturer": "manufacturer 2",
                "substation_id": 1,
                "window_start": "2026-06-25T00:00:00+00:00",
                "window_end": "2026-06-25T06:00:00+00:00",
                "label": "pre_fault",
                "lead_time_bucket": "1-3d",
                "estimated_lead_time_hours": 36.0,
            }
        ]
    )
    out = _context_frame(preprocessed, labels)
    assert out.loc[0, "label"] == ""
    assert out.loc[0, "lead_time_bucket"] == ""
    assert pd.isna(out.loc[0, "estimated_lead_time_hours"])
