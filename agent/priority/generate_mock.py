"""목 데이터 생성기 (Codex 대역).

데모 한 사이클을 위해 `data/mock/mock_ml_output.csv` 를 계약(`data/mock/README.md`)대로
≈300행 생성한다. 결정성을 위해 고정 시드를 쓴다.

가정(assumption): 실제 데모에서는 Codex가 이 파일을 만들지만, 본 자율 실행 환경에는 Codex가
없으므로 동일 계약을 따르는 생성기를 직접 둔다. pre_fault 윈도우일수록 anomaly/risk/임박
리드타임 확률이 높아지는 단조 신호 + 잡음으로, priority 모델이 학습 가능한 구조를 만든다.

실행: ``uv run python -m agent.priority.generate_mock``
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from agent.io import paths
from agent.priority import contracts

SEED = 20260625
N_ROWS = 300
PRE_FAULT_RATIO = 0.45

CONFIG_TYPES = [
    "sh",
    "sh_dhw",
    "sh_dhw_with_sub_circuits",
    "sh_with_buffer_tank",
    "sh_with_sub_circuits",
]
NUMERIC_SENSORS = [
    "s_hc1_supply_temperature",
    "p_net_meter_flow",
    "p_hc1_return_temperature",
    "s_dhw_supply_temperature",
    "p_net_supply_temperature",
    "p_net_return_temperature",
    "s_dhw_upper_storage_temperature",
]
BUCKET_URGENCY = {"0-24h": 1.0, "1-3d": 0.6, "3-7d": 0.33}
BUCKET_HOURS = {"0-24h": (4, 24), "1-3d": (24, 72), "3-7d": (72, 168)}
BUCKET_INDEX = {"0-24h": 0, "1-3d": 1, "3-7d": 2}
FAULT_LABELS = ["pump_degradation", "heat_exchanger_fouling", "valve_fault", "sensor_drift"]


def _risk_level(p: float) -> str:
    # plan thresholds 0.22 / 0.44 / 0.90
    if p >= 0.90:
        return "critical"
    if p >= 0.44:
        return "high"
    if p >= 0.22:
        return "medium"
    return "low"


def _clip01(x: float) -> float:
    return float(min(1.0, max(0.0, x)))


def generate(n_rows: int = N_ROWS, seed: int = SEED) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    base = np.datetime64("2026-04-01T00:00:00")
    rows = []
    for i in range(n_rows):
        manufacturer = f"manufacturer_{rng.integers(1, 3)}"
        substation_id = int(rng.integers(1, 19))
        # 윈도우: base + (0..240) * 6h step, 6시간 폭
        start = base + np.timedelta64(int(rng.integers(0, 240)) * 6, "h")
        end = start + np.timedelta64(6, "h")

        is_pre_fault = rng.random() < PRE_FAULT_RATIO
        config = CONFIG_TYPES[int(rng.integers(0, len(CONFIG_TYPES)))]
        has_dhw = 1 if "dhw" in config else 0
        has_buffer = 1 if "buffer" in config else 0

        if is_pre_fault:
            bucket = rng.choice(["0-24h", "1-3d", "3-7d"], p=[0.4, 0.35, 0.25])
            u = BUCKET_URGENCY[bucket]
            anomaly = _clip01(0.30 + 0.55 * u + rng.normal(0, 0.08))
            risk_p = _clip01(0.30 + 0.58 * u + rng.normal(0, 0.07))
            # leadtime 확률: 진짜 bucket에 질량 집중(신뢰도=u 비례)
            conf = _clip01(0.55 + 0.35 * u + rng.normal(0, 0.05))
            probs = np.array([0.15, 0.15, 0.15]) + rng.random(3) * 0.1
            probs[BUCKET_INDEX[bucket]] += conf
            probs = probs / probs.sum()
            label = contracts.NORMAL_LABEL if False else "pre_fault"
            lo, hi = BUCKET_HOURS[bucket]
            est_hours = float(rng.uniform(lo, hi))
            fault_label = FAULT_LABELS[int(rng.integers(0, len(FAULT_LABELS)))]
            k = int(rng.integers(1, 4))
            sensors = ";".join(
                rng.choice(NUMERIC_SENSORS, size=k, replace=False).tolist()
            )
        else:
            bucket = None
            anomaly = _clip01(rng.normal(0.10, 0.05))
            risk_p = _clip01(rng.normal(0.08, 0.05))
            probs = np.array([0.2, 0.2, 0.2]) + rng.random(3) * 0.15
            probs = probs / probs.sum()
            label = "normal"
            est_hours = np.nan
            fault_label = ""
            sensors = ""

        pred_idx = int(np.argmax(probs))
        pred_bucket = contracts.LEAD_TIME_BUCKETS[pred_idx]
        confidence = float(probs[pred_idx])
        true_idx = BUCKET_INDEX[bucket] if bucket else pred_idx
        bucket_distance = abs(pred_idx - true_idx)
        risk_score = float(min(100.0, max(0.0, risk_p * 100 + rng.normal(0, 3))))

        rows.append(
            {
                "manufacturer": manufacturer,
                "substation_id": substation_id,
                "window_start": str(start),
                "window_end": str(end),
                "anomaly_score": round(anomaly, 4),
                "risk_score": round(risk_score, 2),
                "risk_probability": round(risk_p, 4),
                "risk_level_calibrated": _risk_level(risk_p),
                "predicted_lead_time_bucket": pred_bucket,
                "predicted_lead_time_confidence": round(confidence, 4),
                "leadtime_prob_0-24h": round(float(probs[0]), 4),
                "leadtime_prob_1-3d": round(float(probs[1]), 4),
                "leadtime_prob_3-7d": round(float(probs[2]), 4),
                "lead_time_bucket_distance": bucket_distance,
                "days_since_last_fault_event": round(float(rng.uniform(5, 400)), 1),
                "days_since_last_task_event": round(float(rng.uniform(1, 200)), 1),
                "days_since_last_any_event": round(float(rng.uniform(1, 200)), 1),
                "configuration_type": config,
                "has_dhw": has_dhw,
                "has_buffer_tank": has_buffer,
                "main_abnormal_sensors": sensors,
                "label": label,
                "fault_label": fault_label,
                "estimated_lead_time_hours": (
                    round(est_hours, 1) if not np.isnan(est_hours) else ""
                ),
                "lead_time_bucket": bucket if bucket else "",
            }
        )

    df = pd.DataFrame(rows, columns=contracts.MOCK_ML_OUTPUT_COLUMNS)
    return df


def main() -> None:
    df = generate()
    paths.ensure_dir(paths.MOCK_DIR)
    df.to_csv(paths.MOCK_ML_OUTPUT, index=False, encoding="utf-8")
    n_pre = int((df["label"] == "pre_fault").sum())
    print(f"[generate_mock] wrote {paths.MOCK_ML_OUTPUT} rows={len(df)} "
          f"pre_fault={n_pre} normal={len(df) - n_pre}")


if __name__ == "__main__":
    main()
