from __future__ import annotations

import numpy as np
import pandas as pd

from . import config
from .common import write_json
from .m1_specialist_gates import score_m1_specialist_gates
from .operational import write_agent_contract_docs


def _markdown_table(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "(empty)"
    data = frame.copy().fillna("")
    columns = [str(column) for column in data.columns]
    lines = ["| " + " | ".join(columns) + " |", "| " + " | ".join(["---"] * len(columns)) + " |"]
    for _, row in data.iterrows():
        lines.append("| " + " | ".join(str(row[column]).replace("|", "\\|") for column in data.columns) + " |")
    return "\n".join(lines)


def _level(
    score: pd.Series,
    high_threshold: float,
    urgent_threshold: float,
    medium_threshold: float | None = None,
) -> pd.Series:
    if medium_threshold is None:
        medium_threshold = max(20.0, high_threshold * 0.60)
    return pd.Series(
        np.select(
            [score.ge(urgent_threshold), score.ge(high_threshold), score.ge(medium_threshold)],
            ["urgent", "high", "medium"],
            default="low",
        ),
        index=score.index,
    )


def _row_metrics(frame: pd.DataFrame, pred_column: str, score_column: str, split: str, policy: str) -> dict[str, object]:
    part = frame.loc[frame["split_time_based"].eq(split)].copy()
    y_true = part["label"].eq("pre_fault")
    y_pred = pd.to_numeric(part[pred_column], errors="coerce").fillna(0).astype(int).eq(1)
    tp = int((y_true & y_pred).sum())
    fp = int((~y_true & y_pred).sum())
    fn = int((y_true & ~y_pred).sum())
    tn = int((~y_true & ~y_pred).sum())
    return {
        "policy": policy,
        "split": split,
        "metric_scope": "row",
        "row_count": int(len(part)),
        "precision": tp / max(1, tp + fp),
        "recall": tp / max(1, tp + fn),
        "false_positive_rate": fp / max(1, fp + tn),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "mean_score": float(pd.to_numeric(part[score_column], errors="coerce").mean()) if score_column in part.columns else np.nan,
    }


def _fault_event_metrics(frame: pd.DataFrame, pred_column: str, split: str, policy: str) -> dict[str, object]:
    part = frame.loc[
        frame["split_time_based"].eq(split)
        & frame["label"].eq("pre_fault")
        & frame["fault_event_id"].notna()
        & frame["fault_event_id"].astype(str).ne(""),
    ].copy()
    total = int(part["fault_event_id"].nunique())
    detected = 0
    if total:
        detected = int(
            part.assign(_pred=pd.to_numeric(part[pred_column], errors="coerce").fillna(0).astype(int))
            .groupby("fault_event_id")["_pred"]
            .max()
            .sum()
        )
    return {
        "policy": policy,
        "split": split,
        "metric_scope": "fault_event",
        "fault_events": total,
        "detected_fault_events": detected,
        "fault_event_recall": detected / max(1, total),
        "note": "normal-event 기준 FPR은 별도 event contract가 없어 row false_positive_rate를 비교 기준으로 사용한다.",
    }


def _choose_threshold(frame: pd.DataFrame, score_column: str) -> float:
    validation = frame.loc[frame["split_time_based"].eq("validation")].copy()
    if validation.empty:
        return 50.0
    y_true = validation["label"].eq("pre_fault")
    scores = pd.to_numeric(validation[score_column], errors="coerce").fillna(0.0)
    best: tuple[float, float, float] | None = None
    unconstrained_best: tuple[float, float, float] | None = None
    for threshold in np.linspace(20.0, 95.0, 31):
        pred = scores.ge(threshold)
        tp = int((y_true & pred).sum())
        fp = int((~y_true & pred).sum())
        fn = int((y_true & ~pred).sum())
        tn = int((~y_true & ~pred).sum())
        precision = tp / max(1, tp + fp)
        recall = tp / max(1, tp + fn)
        fpr = fp / max(1, fp + tn)
        f1 = 2 * precision * recall / max(1e-12, precision + recall)
        if fpr <= config.PRIORITY_TARGET_FALSE_ALARM:
            candidate = (recall, precision, float(threshold))
            if best is None or candidate > best:
                best = candidate
        unconstrained_candidate = (f1, -fpr, float(threshold))
        if unconstrained_best is None or unconstrained_candidate > unconstrained_best:
            unconstrained_best = unconstrained_candidate
    return (best if best is not None else unconstrained_best)[2]


def _add_policy(frame: pd.DataFrame, score_column: str, prefix: str) -> tuple[pd.DataFrame, float, float]:
    result = frame.copy()
    score = pd.to_numeric(result[score_column], errors="coerce").fillna(0.0)
    high_threshold = _choose_threshold(result, score_column)
    validation_scores = score.loc[result["split_time_based"].eq("validation")]
    urgent_threshold = min(95.0, max(high_threshold + 15.0, float(validation_scores.quantile(0.90)) if not validation_scores.empty else high_threshold + 15.0))
    level_column = f"{prefix}_level"
    label_column = f"{prefix}_high_label"
    result[level_column] = _level(score, high_threshold, urgent_threshold)
    result[label_column] = result[level_column].isin(["high", "urgent"]).astype("int8")
    return result, high_threshold, urgent_threshold


def _add_fixed_policy(
    frame: pd.DataFrame,
    score_column: str,
    prefix: str,
    *,
    high_threshold: float,
    urgent_threshold: float,
    medium_threshold: float | None = None,
) -> pd.DataFrame:
    result = frame.copy()
    score = pd.to_numeric(result[score_column], errors="coerce").fillna(0.0)
    level_column = f"{prefix}_level"
    label_column = f"{prefix}_high_label"
    result[level_column] = _level(
        score,
        high_threshold,
        urgent_threshold,
        medium_threshold,
    )
    result[label_column] = result[level_column].isin(["high", "urgent"]).astype("int8")
    return result


def _evidence_gate_sweep(frame: pd.DataFrame) -> pd.DataFrame:
    """Evaluate label-free pre-event/leadtime OR gates on the fixed splits."""
    work = frame.copy()
    pre_event = pd.to_numeric(
        work["m1_specialist_pre_event_probability"], errors="coerce"
    ).fillna(0.0)
    leadtime = pd.to_numeric(
        work["m1_specialist_leadtime_urgency"], errors="coerce"
    ).fillna(0.0)
    rows: list[dict[str, object]] = []
    pre_thresholds = np.round(np.arange(0.95, 0.996, 0.005), 3)
    lead_thresholds = np.round(np.arange(0.94, 0.991, 0.005), 3)
    for pre_threshold in pre_thresholds:
        for lead_threshold in lead_thresholds:
            work["_evidence_gate_pred"] = (
                pre_event.ge(float(pre_threshold))
                | leadtime.ge(float(lead_threshold))
            ).astype("int8")
            work["_evidence_gate_score"] = np.maximum(
                100.0 * pre_event,
                100.0 * leadtime
                + 100.0 * (float(pre_threshold) - float(lead_threshold)),
            ).clip(upper=100.0)
            policy = f"pre_{pre_threshold:.3f}_or_lead_{lead_threshold:.3f}"
            for split in ["train", "validation", "holdout"]:
                row = _row_metrics(
                    work,
                    "_evidence_gate_pred",
                    "_evidence_gate_score",
                    split,
                    policy,
                )
                event = _fault_event_metrics(
                    work,
                    "_evidence_gate_pred",
                    split,
                    policy,
                )
                row.update(
                    {
                        "pre_event_threshold": float(pre_threshold),
                        "leadtime_threshold": float(lead_threshold),
                        "fault_events": event["fault_events"],
                        "detected_fault_events": event["detected_fault_events"],
                        "fault_event_recall": event["fault_event_recall"],
                        "selected_official_v3": bool(
                            np.isclose(pre_threshold, config.M1_EVIDENCE_PRE_EVENT_HIGH_THRESHOLD)
                            and np.isclose(lead_threshold, config.M1_EVIDENCE_LEADTIME_HIGH_THRESHOLD)
                        ),
                    }
                )
                precision = float(row["precision"])
                recall = float(row["recall"])
                row["f1"] = 2.0 * precision * recall / max(1e-12, precision + recall)
                rows.append(row)
    return pd.DataFrame(rows)


def _band_evidence_score(
    values: pd.Series,
    medium_input: float,
    high_input: float,
    urgent_input: float,
) -> pd.Series:
    """Map a probability-like input into monotonic low/medium/high/urgent bands."""
    value = pd.to_numeric(values, errors="coerce").fillna(0.0).clip(0.0, 1.0)
    low = 90.0 * value / max(medium_input, 1e-12)
    medium = 90.0 + 9.0 * (value - medium_input) / max(high_input - medium_input, 1e-12)
    high = 99.0 + 0.8 * (value - high_input) / max(urgent_input - high_input, 1e-12)
    urgent = 99.8 + 0.2 * (value - urgent_input) / max(1.0 - urgent_input, 1e-12)
    return pd.Series(
        np.select(
            [value.ge(urgent_input), value.ge(high_input), value.ge(medium_input)],
            [urgent, high, medium],
            default=low,
        ),
        index=value.index,
    ).clip(0.0, 100.0)


def _risk_pre_event_gate_sweep(frame: pd.DataFrame) -> pd.DataFrame:
    """Evaluate the official v4 label-free Risk/pre-event OR gate."""
    work = frame.copy()
    risk = pd.to_numeric(work["risk_score"], errors="coerce").fillna(0.0)
    pre_event = pd.to_numeric(
        work["m1_specialist_pre_event_probability"], errors="coerce"
    ).fillna(0.0)
    rows: list[dict[str, object]] = []
    risk_thresholds = [0.70, 0.74, 0.76, 0.78, 0.80, 0.82, 0.85, 0.88, 0.90, 0.92]
    pre_thresholds = [0.95, 0.97, 0.975, 0.98, 0.985, 0.99, 0.995]
    for risk_threshold in risk_thresholds:
        for pre_threshold in pre_thresholds:
            work["_v4_gate_pred"] = (
                risk.ge(risk_threshold) | pre_event.ge(pre_threshold)
            ).astype("int8")
            work["_v4_gate_score"] = np.maximum(100.0 * risk, 100.0 * pre_event)
            policy = f"risk_{risk_threshold:.3f}_or_pre_{pre_threshold:.3f}"
            for split in ["train", "validation", "holdout"]:
                row = _row_metrics(work, "_v4_gate_pred", "_v4_gate_score", split, policy)
                event = _fault_event_metrics(work, "_v4_gate_pred", split, policy)
                row.update(
                    {
                        "risk_threshold": risk_threshold,
                        "pre_event_threshold": pre_threshold,
                        "fault_events": event["fault_events"],
                        "detected_fault_events": event["detected_fault_events"],
                        "fault_event_recall": event["fault_event_recall"],
                        "selected_official_v4": bool(
                            np.isclose(risk_threshold, config.M1_RISK_HIGH_THRESHOLD)
                            and np.isclose(pre_threshold, config.M1_PRE_EVENT_HIGH_THRESHOLD)
                        ),
                    }
                )
                precision = float(row["precision"])
                recall = float(row["recall"])
                row["f1"] = 2.0 * precision * recall / max(1e-12, precision + recall)
                rows.append(row)
    return pd.DataFrame(rows)


def _agreement(row: pd.Series) -> str:
    current_high = str(row.get("current_best_priority_level", row.get("priority_level", ""))).lower() in {"high", "urgent"}
    specialist_high = str(row.get("m1_specialist_priority_level", "")).lower() in {"high", "urgent"}
    if current_high and specialist_high:
        return "both_high"
    if current_high and not specialist_high:
        return "current_only_high"
    if specialist_high and not current_high:
        return "m1_specialist_only_high"
    return "both_not_high"


def _reason(row: pd.Series) -> str:
    parts = [
        f"current_best_priority={row.get('current_best_priority_level', row.get('priority_level', ''))}",
        f"m1_specialist_priority={row.get('m1_specialist_priority_level', '')}",
        f"m1_hybrid_priority={row.get('m1_hybrid_priority_level', '')}",
        f"m1_evidence_priority={row.get('m1_evidence_priority_level', '')}",
        f"evidence_trigger={row.get('m1_evidence_trigger', '')}",
        f"risk_pre_event_priority={row.get('m1_risk_pre_event_priority_level', '')}",
        f"risk_pre_event_trigger={row.get('m1_risk_pre_event_trigger', '')}",
        f"agreement={row.get('m1_priority_agreement', '')}",
        f"fault_gate={float(pd.to_numeric(row.get('m1_specialist_fault_probability'), errors='coerce')):.3f}"
        if pd.notna(pd.to_numeric(row.get("m1_specialist_fault_probability"), errors="coerce"))
        else "fault_gate=na",
        f"pre_event={float(pd.to_numeric(row.get('m1_specialist_pre_event_probability'), errors='coerce')):.3f}"
        if pd.notna(pd.to_numeric(row.get("m1_specialist_pre_event_probability"), errors="coerce"))
        else "pre_event=na",
        f"fault_group={row.get('m1_specialist_fault_group', '')}",
    ]
    return "; ".join(parts)


def _action(row: pd.Series) -> str:
    agreement = row.get("m1_priority_agreement")
    hybrid = row.get("m1_hybrid_priority_level")
    if agreement == "both_high" or hybrid == "urgent":
        return "M1 specialist와 current best가 모두 높게 본 후보다. 현장 점검 우선순위를 높인다."
    if agreement == "m1_specialist_only_high":
        return "M1 specialist만 높게 본 후보다. compact13/gate 근거를 검토하고 보조 점검 후보로 올린다."
    if agreement == "current_only_high":
        return "current best만 높게 본 후보다. M1 specialist 불일치 사유를 확인한 뒤 기존 우선순위를 유지한다."
    return "현재는 낮은 우선순위다. 다음 window에서 지속 여부를 모니터링한다."


def _action_v2(row: pd.Series) -> str:
    level = row.get("m1_risk_pre_event_priority_level")
    trigger = row.get("m1_risk_pre_event_trigger", "none")
    if level == "urgent":
        return f"urgent review: high-confidence evidence gate triggered by {trigger}."
    if level == "high":
        return f"priority review: evidence gate triggered by {trigger}; confirm before dispatch."
    if level == "medium":
        return "monitor closely: evidence is elevated but remains below the high-priority gate."
    return "monitor: no high-confidence Risk or pre-event evidence in the current window."


def _load_base_frame() -> pd.DataFrame:
    if not config.AGENT_CARD_PATH.exists():
        raise FileNotFoundError("Run agent_card before m1_specialist.")
    if not config.M1_SPECIALIST_GATE_SCORES_PATH.exists():
        score_m1_specialist_gates()
    agent = pd.read_csv(config.AGENT_CARD_PATH)
    previous_prefixes = ("m1_specialist_", "m1_hybrid_", "m1_evidence_", "m1_risk_pre_event_")
    previous_columns = [column for column in agent.columns if column.startswith(previous_prefixes)]
    agent = agent.drop(columns=previous_columns, errors="ignore")
    for column in ["m1_priority_agreement", "priority_source", "priority_high_label"]:
        if column in agent.columns:
            agent = agent.drop(columns=[column])
    specialist = pd.read_csv(config.M1_SPECIALIST_GATE_SCORES_PATH)
    windows = pd.read_csv(config.TRAINABLE_WINDOWS_PATH)
    split = windows[[*config.KEY_COLUMNS, "split_time_based"]].drop_duplicates(config.KEY_COLUMNS)
    frame = agent.merge(split, on=config.KEY_COLUMNS, how="left", validate="one_to_one")
    specialist_cols = [
        column
        for column in specialist.columns
        if column not in {"label", "fault_label", "fault_event_id"} or column in config.KEY_COLUMNS
    ]
    frame = frame.merge(
        specialist[specialist_cols].drop_duplicates(config.KEY_COLUMNS),
        on=config.KEY_COLUMNS,
        how="left",
        validate="one_to_one",
    )
    frame = frame.loc[frame["manufacturer"].astype(str).eq(config.M1_MANUFACTURER)].copy()
    if frame.empty:
        raise ValueError("M1 specialist frame is empty.")
    return frame


def build_m1_specialist_outputs() -> pd.DataFrame:
    config.ensure_dirs()
    frame = _load_base_frame()
    if "current_best_priority_score" not in frame.columns:
        frame["current_best_priority_score"] = pd.to_numeric(frame["priority_score"], errors="coerce").fillna(0.0)
    else:
        existing_priority_score = pd.to_numeric(frame.get("priority_score"), errors="coerce").fillna(0.0)
        frame["current_best_priority_score"] = pd.to_numeric(
            frame["current_best_priority_score"],
            errors="coerce",
        ).fillna(existing_priority_score)
    if "current_best_priority_level" not in frame.columns:
        frame["current_best_priority_level"] = frame["priority_level"].astype(str)
    else:
        current_level = frame["current_best_priority_level"].replace("", np.nan)
        frame["current_best_priority_level"] = current_level.fillna(frame["priority_level"]).astype(str)
    frame["m1_specialist_priority_score"] = pd.to_numeric(frame["m1_specialist_priority_score"], errors="coerce").fillna(0.0)
    frame["legacy_priority_score"] = (
        config.LEGACY_M1_HYBRID_CURRENT_BEST_WEIGHT * frame["current_best_priority_score"]
        + config.LEGACY_M1_HYBRID_SPECIALIST_WEIGHT * frame["m1_specialist_priority_score"]
    )
    frame["legacy_priority_level"] = _level(
        frame["legacy_priority_score"],
        config.LEGACY_M1_HYBRID_HIGH_THRESHOLD,
        config.LEGACY_M1_HYBRID_URGENT_THRESHOLD,
    )
    frame["legacy_priority_high_label"] = frame["legacy_priority_level"].isin(["high", "urgent"]).astype("int8")
    frame["m1_hybrid_priority_score"] = (
        config.M1_HYBRID_CURRENT_BEST_WEIGHT * frame["current_best_priority_score"]
        + config.M1_HYBRID_SPECIALIST_WEIGHT * frame["m1_specialist_priority_score"]
    )
    frame, specialist_high, specialist_urgent = _add_policy(frame, "m1_specialist_priority_score", "m1_specialist_priority")
    hybrid_high = config.M1_HYBRID_HIGH_THRESHOLD
    hybrid_urgent = config.M1_HYBRID_URGENT_THRESHOLD
    frame = _add_fixed_policy(
        frame,
        "m1_hybrid_priority_score",
        "m1_hybrid_priority",
        high_threshold=hybrid_high,
        urgent_threshold=hybrid_urgent,
    )
    pre_event_probability = pd.to_numeric(
        frame["m1_specialist_pre_event_probability"], errors="coerce"
    ).fillna(0.0).clip(0.0, 1.0)
    leadtime_urgency = pd.to_numeric(
        frame["m1_specialist_leadtime_urgency"], errors="coerce"
    ).fillna(0.0).clip(0.0, 1.0)
    frame["m1_evidence_pre_event_score"] = 100.0 * pre_event_probability
    frame["m1_evidence_leadtime_score"] = (
        100.0 * leadtime_urgency + config.M1_EVIDENCE_LEADTIME_SCORE_OFFSET
    ).clip(upper=100.0)
    frame["m1_evidence_priority_score"] = np.maximum(
        frame["m1_evidence_pre_event_score"],
        frame["m1_evidence_leadtime_score"],
    )
    frame = _add_fixed_policy(
        frame,
        "m1_evidence_priority_score",
        "m1_evidence_priority",
        medium_threshold=config.M1_EVIDENCE_MEDIUM_THRESHOLD,
        high_threshold=config.M1_EVIDENCE_HIGH_THRESHOLD,
        urgent_threshold=config.M1_EVIDENCE_URGENT_THRESHOLD,
    )
    pre_trigger = pre_event_probability.ge(config.M1_EVIDENCE_PRE_EVENT_HIGH_THRESHOLD)
    lead_trigger = leadtime_urgency.ge(config.M1_EVIDENCE_LEADTIME_HIGH_THRESHOLD)
    frame["m1_evidence_trigger"] = np.select(
        [pre_trigger & lead_trigger, pre_trigger, lead_trigger],
        ["pre_event|leadtime", "pre_event", "leadtime"],
        default="none",
    )
    risk_score = pd.to_numeric(frame["risk_score"], errors="coerce").fillna(0.0).clip(0.0, 1.0)
    risk_band_score = _band_evidence_score(
        risk_score,
        config.M1_RISK_MEDIUM_THRESHOLD,
        config.M1_RISK_HIGH_THRESHOLD,
        config.M1_RISK_URGENT_THRESHOLD,
    )
    pre_event_band_score = _band_evidence_score(
        pre_event_probability,
        config.M1_PRE_EVENT_MEDIUM_THRESHOLD,
        config.M1_PRE_EVENT_HIGH_THRESHOLD,
        config.M1_PRE_EVENT_URGENT_THRESHOLD,
    )
    frame["m1_risk_pre_event_priority_score"] = np.maximum(
        risk_band_score,
        pre_event_band_score,
    )
    frame = _add_fixed_policy(
        frame,
        "m1_risk_pre_event_priority_score",
        "m1_risk_pre_event_priority",
        medium_threshold=config.M1_RISK_PRE_EVENT_MEDIUM_THRESHOLD,
        high_threshold=config.M1_RISK_PRE_EVENT_HIGH_THRESHOLD,
        urgent_threshold=config.M1_RISK_PRE_EVENT_URGENT_THRESHOLD,
    )
    risk_trigger = risk_score.ge(config.M1_RISK_HIGH_THRESHOLD)
    v4_pre_trigger = pre_event_probability.ge(config.M1_PRE_EVENT_HIGH_THRESHOLD)
    frame["m1_risk_pre_event_trigger"] = np.select(
        [risk_trigger & v4_pre_trigger, risk_trigger, v4_pre_trigger],
        ["risk|pre_event", "risk", "pre_event"],
        default="none",
    )
    frame["m1_priority_agreement"] = frame.apply(_agreement, axis=1)
    frame["m1_priority_review_required"] = frame["m1_priority_agreement"].isin(["m1_specialist_only_high", "current_only_high"])
    frame["m1_why_reason"] = frame.apply(_reason, axis=1)
    frame["m1_recommended_action"] = frame.apply(_action_v2, axis=1)

    current_pred = frame["current_best_priority_level"].isin(["high", "urgent"]).astype("int8")
    frame["current_best_priority_high_label"] = current_pred
    metrics: list[dict[str, object]] = []
    policies = [
        ("current_best_priority", "current_best_priority_high_label", "current_best_priority_score"),
        ("m1_specialist_priority", "m1_specialist_priority_high_label", "m1_specialist_priority_score"),
        ("legacy_priority", "legacy_priority_high_label", "legacy_priority_score"),
        ("m1_hybrid_priority", "m1_hybrid_priority_high_label", "m1_hybrid_priority_score"),
        ("m1_evidence_priority", "m1_evidence_priority_high_label", "m1_evidence_priority_score"),
        ("m1_risk_pre_event_priority", "m1_risk_pre_event_priority_high_label", "m1_risk_pre_event_priority_score"),
    ]
    for split in ["train", "validation", "holdout"]:
        for policy, pred_column, score_column in policies:
            metrics.append(_row_metrics(frame, pred_column, score_column, split, policy))
            metrics.append(_fault_event_metrics(frame, pred_column, split, policy))

    comparison = pd.DataFrame(metrics)
    frame["priority_source"] = config.M1_PRIORITY_SOURCE
    frame["policy_version"] = config.M1_PRIORITY_POLICY_VERSION
    frame["current_best_weight"] = np.nan
    frame["m1_specialist_weight"] = np.nan
    frame["decision_basis"] = (
        "label-free v4 gate: restored risk_score >= 0.78 OR pre_event_probability >= 0.99; "
        "urgent when risk >= 0.92 OR pre_event >= 0.998; band score preserves level ordering"
    )
    frame["priority_score"] = frame["m1_risk_pre_event_priority_score"]
    frame["priority_level"] = frame["m1_risk_pre_event_priority_level"]
    frame["priority_high_label"] = frame["m1_risk_pre_event_priority_high_label"]
    frame["why_reason"] = frame["m1_why_reason"]
    frame["recommended_action"] = frame["m1_recommended_action"]
    base_review = frame.get("review_required", pd.Series(False, index=frame.index)).fillna(False).astype(bool)
    gate_review = frame.get("m1_specialist_gate_review_required", pd.Series(False, index=frame.index)).fillna(False).astype(bool)
    priority_review = frame["m1_priority_review_required"].fillna(False).astype(bool)
    frame["review_required"] = base_review | gate_review | priority_review
    existing_review = frame.get("review_reasons", pd.Series("", index=frame.index)).fillna("").astype(str)
    gate_review_text = frame.get("m1_specialist_gate_review_reasons", pd.Series("", index=frame.index)).fillna("").astype(str)
    m1_review_text = np.where(priority_review, "m1_priority_disagreement", "")
    frame["review_reasons"] = [
        "|".join([part for part in [a, b, c] if str(part)])
        for a, b, c in zip(existing_review, gate_review_text, m1_review_text)
    ]
    _evidence_gate_sweep(frame).to_csv(
        config.M1_EVIDENCE_GATE_SWEEP_PATH,
        index=False,
        encoding="utf-8-sig",
        float_format=config.CSV_FLOAT_FORMAT,
        lineterminator=config.CSV_LINE_TERMINATOR,
    )
    _risk_pre_event_gate_sweep(frame).to_csv(
        config.M1_RISK_PRE_EVENT_GATE_SWEEP_PATH,
        index=False,
        encoding="utf-8-sig",
        float_format=config.CSV_FLOAT_FORMAT,
        lineterminator=config.CSV_LINE_TERMINATOR,
    )
    frame.to_csv(config.M1_SPECIALIST_SCORES_PATH, index=False, encoding="utf-8-sig", float_format=config.CSV_FLOAT_FORMAT, lineterminator=config.CSV_LINE_TERMINATOR)
    comparison.to_csv(config.M1_SPECIALIST_COMPARISON_PATH, index=False, encoding="utf-8-sig", float_format=config.CSV_FLOAT_FORMAT, lineterminator=config.CSV_LINE_TERMINATOR)
    agent_columns = [
        *config.KEY_COLUMNS,
        "configuration_type",
        "label",
        "fault_label",
        "fault_event_id",
        "split_time_based",
        "priority_score",
        "priority_level",
        "risk_score",
        "risk_level_calibrated",
        "leadtime_urgency_score",
        "anomaly_evidence_event_label",
        "anomaly_evidence_source",
        "m1_specialist_fault_probability",
        "m1_specialist_task_probability",
        "m1_specialist_activity_probability",
        "m1_specialist_pre_event_probability",
        "m1_specialist_primary_state",
        "m1_specialist_fault_group",
        "m1_specialist_group_weight",
        "m1_specialist_priority_score",
        "m1_specialist_priority_level",
        "m1_hybrid_priority_score",
        "m1_hybrid_priority_level",
        "m1_evidence_pre_event_score",
        "m1_evidence_leadtime_score",
        "m1_evidence_priority_score",
        "m1_evidence_priority_level",
        "m1_evidence_trigger",
        "m1_risk_pre_event_priority_score",
        "m1_risk_pre_event_priority_level",
        "m1_risk_pre_event_trigger",
        "m1_priority_agreement",
        "m1_specialist_gate_review_required",
        "m1_specialist_gate_review_reasons",
        "m1_why_reason",
        "m1_recommended_action",
    ]
    promoted_agent = frame[[column for column in config.AGENT_OUTPUT_COLUMNS if column in frame.columns]].copy()
    for column in config.AGENT_OUTPUT_COLUMNS:
        if column not in promoted_agent.columns:
            promoted_agent[column] = ""
    promoted_agent = promoted_agent[config.AGENT_OUTPUT_COLUMNS].copy()
    promoted_agent.to_csv(config.AGENT_CARD_PATH, index=False, encoding="utf-8-sig", float_format=config.CSV_FLOAT_FORMAT, lineterminator=config.CSV_LINE_TERMINATOR)
    promoted_agent.to_csv(config.M1_SPECIALIST_AGENT_CARD_PATH, index=False, encoding="utf-8-sig", float_format=config.CSV_FLOAT_FORMAT, lineterminator=config.CSV_LINE_TERMINATOR)
    write_agent_contract_docs()

    holdout = comparison.loc[comparison["split"].eq("holdout")].copy()
    lines = [
        "# M1 Specialist 보고서",
        "",
        "이 보고서는 M1-only 범위에서 current-best priority와 M1 specialist priority를 병렬 비교한다.",
        "",
        "## 범위",
        "",
        f"- manufacturer filter: `{config.M1_MANUFACTURER}`",
        "- 이 저장소는 M1 row만 대상으로 fit/score/validation을 수행한다.",
        "- 공식 M1 agent card의 `priority_score`, `priority_level`은 label-free Risk/pre-event gate v4다.",
        f"- 공식 정책 버전: `{config.M1_PRIORITY_POLICY_VERSION}`",
        "- 공식 조건: restored Risk score >= 0.78 또는 pre-event probability >= 0.99",
        "- 원래 current-best priority는 `current_best_priority_score`, `current_best_priority_level`로 보존한다.",
        "- 요청 v2 0.72/0.28은 `m1_hybrid_priority_score`, `m1_hybrid_priority_level`로 보존한다.",
        "- 이전 v1 0.65/0.35는 `legacy_priority_score`, `legacy_priority_level`로 보존한다.",
        "- `m1_specialist_*` 컬럼은 M1 specialist 병렬 근거로 보존한다.",
        "",
        "## Threshold",
        "",
        f"- m1_specialist high 기준: {specialist_high:.3f}",
        f"- m1_specialist urgent 기준: {specialist_urgent:.3f}",
        f"- m1_hybrid high 기준: {hybrid_high:.3f}",
        f"- m1_hybrid urgent 기준: {hybrid_urgent:.3f}",
        f"- evidence medium 기준: {config.M1_EVIDENCE_MEDIUM_THRESHOLD:.3f}",
        f"- evidence high 기준: {config.M1_EVIDENCE_HIGH_THRESHOLD:.3f}",
        f"- evidence urgent 기준: {config.M1_EVIDENCE_URGENT_THRESHOLD:.3f}",
        f"- v4 Risk high/urgent 기준: {config.M1_RISK_HIGH_THRESHOLD:.3f} / {config.M1_RISK_URGENT_THRESHOLD:.3f}",
        f"- v4 pre-event high/urgent 기준: {config.M1_PRE_EVENT_HIGH_THRESHOLD:.3f} / {config.M1_PRE_EVENT_URGENT_THRESHOLD:.3f}",
        "",
        "## Holdout 지표",
        _markdown_table(holdout),
    ]
    config.M1_SPECIALIST_REPORT_PATH.write_text("\n".join(lines), encoding="utf-8", newline="\n")

    scope_payload = {
        "scope": config.PROJECT_SCOPE,
        "manufacturer_filter": config.M1_MANUFACTURER,
        "rows": int(len(frame)),
        "label_counts": frame["label"].value_counts(dropna=False).to_dict(),
        "split_counts": frame["split_time_based"].value_counts(dropna=False).to_dict(),
        "fault_event_count": int(frame.loc[frame["label"].eq("pre_fault"), "fault_event_id"].nunique()),
        "m1_specialist_thresholds": {
            "high": specialist_high,
            "urgent": specialist_urgent,
        },
        "m1_hybrid_thresholds": {
            "high": hybrid_high,
            "urgent": hybrid_urgent,
        },
        "policy_version": config.M1_PRIORITY_POLICY_VERSION,
        "official_priority_source": config.M1_PRIORITY_SOURCE,
        "official_priority_policy": {
            "policy_type": "label_free_risk_pre_event_gate",
            "risk_medium_threshold": config.M1_RISK_MEDIUM_THRESHOLD,
            "risk_high_threshold": config.M1_RISK_HIGH_THRESHOLD,
            "risk_urgent_threshold": config.M1_RISK_URGENT_THRESHOLD,
            "pre_event_medium_threshold": config.M1_PRE_EVENT_MEDIUM_THRESHOLD,
            "pre_event_high_threshold": config.M1_PRE_EVENT_HIGH_THRESHOLD,
            "pre_event_urgent_threshold": config.M1_PRE_EVENT_URGENT_THRESHOLD,
            "medium_threshold": config.M1_RISK_PRE_EVENT_MEDIUM_THRESHOLD,
            "high_threshold": config.M1_RISK_PRE_EVENT_HIGH_THRESHOLD,
            "urgent_threshold": config.M1_RISK_PRE_EVENT_URGENT_THRESHOLD,
            "score_formula": "max(piecewise_band(risk), piecewise_band(pre_event))",
            "selection_basis": "Risk 0.78 selected on event-regime validation with row FPR <= 0.05; pre-event 0.99 is the preserved high-confidence gate",
        },
        "previous_v3_priority_policy": {
            "pre_event_high_threshold": config.M1_EVIDENCE_PRE_EVENT_HIGH_THRESHOLD,
            "leadtime_high_threshold": config.M1_EVIDENCE_LEADTIME_HIGH_THRESHOLD,
            "preserved_as": ["m1_evidence_priority_score", "m1_evidence_priority_level"],
        },
        "v2_hybrid_policy": {
            "policy_version": config.M1_HYBRID_POLICY_VERSION,
            "priority_source": config.M1_HYBRID_PRIORITY_SOURCE,
            "current_best_weight": config.M1_HYBRID_CURRENT_BEST_WEIGHT,
            "m1_specialist_weight": config.M1_HYBRID_SPECIALIST_WEIGHT,
            "high_threshold": config.M1_HYBRID_HIGH_THRESHOLD,
            "urgent_threshold": config.M1_HYBRID_URGENT_THRESHOLD,
            "preserved_as": ["m1_hybrid_priority_score", "m1_hybrid_priority_level"],
        },
        "legacy_priority_policy": {
            "policy_version": config.LEGACY_M1_HYBRID_POLICY_VERSION,
            "priority_source": config.LEGACY_M1_HYBRID_PRIORITY_SOURCE,
            "current_best_weight": config.LEGACY_M1_HYBRID_CURRENT_BEST_WEIGHT,
            "m1_specialist_weight": config.LEGACY_M1_HYBRID_SPECIALIST_WEIGHT,
            "high_threshold": config.LEGACY_M1_HYBRID_HIGH_THRESHOLD,
            "urgent_threshold": config.LEGACY_M1_HYBRID_URGENT_THRESHOLD,
            "preserved_as": ["legacy_priority_score", "legacy_priority_level"],
        },
        "current_best_priority_preserved_as": [
            "current_best_priority_score",
            "current_best_priority_level",
        ],
        "third_project_parallel_line": {
            "compact13_features": config.path_label(config.M1_SPECIALIST_COMPACT13_FEATURES_PATH),
            "gate_scores": config.path_label(config.M1_SPECIALIST_GATE_SCORES_PATH),
            "agent_card": config.path_label(config.M1_SPECIALIST_PARALLEL_AGENT_CARD_PATH),
        },
    }
    write_json(config.REPORT_DIR / "m1_specialist_metadata.json", scope_payload)
    config.M1_SCOPE_REPORT_PATH.write_text(
        "\n".join(
            [
                "# M1 범위 점검",
                "",
                f"- 범위: `{config.PROJECT_SCOPE}`",
                f"- 제조사 필터: `{config.M1_MANUFACTURER}`",
                f"- 행 수: {scope_payload['rows']}",
                f"- label 분포: {scope_payload['label_counts']}",
                f"- split 분포: {scope_payload['split_counts']}",
                f"- fault event 수: {scope_payload['fault_event_count']}",
            ]
        ),
        encoding="utf-8",
        newline="\n",
    )
    return frame
