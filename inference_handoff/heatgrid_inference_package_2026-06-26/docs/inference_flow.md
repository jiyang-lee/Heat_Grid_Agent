# Inference Flow

## 1. Raw Input

The service receives operational telemetry per substation. The expected raw shape is the same family as the Predist operational CSV files:

- semicolon delimiter
- `timestamp`
- sensor columns such as `outdoor_temperature`, `p_net_supply_temperature`, `p_net_return_temperature`, `s_hc1_supply_temperature`
- optional control mode/status columns

## 2. Windowing

Rows are grouped into 6 hour non-overlapping windows using:

```text
window_start = floor(timestamp, 6h)
window_end = window_start + 6h
```

Each output row is one `manufacturer + substation_id + window_start + window_end`.

## 3. Feature Engineering

For each numeric sensor column:

- `mean`
- `min`
- `max`
- `std`
- `first`
- `last`
- `delta`
- `missing_count`
- `missing_rate`

Derived gap features:

- `hc1_supply_temperature_gap = s_hc1_supply_temperature - s_hc1_supply_temperature_setpoint`
- `dhw_supply_temperature_gap = s_dhw_supply_temperature - s_dhw_supply_temperature_setpoint`
- `network_temperature_gap = p_net_supply_temperature - p_net_return_temperature`

Time context:

- `hour_of_day`
- `day_of_week`
- `day_of_year`
- `month`
- `is_weekend`
- `is_heating_season`
- `season_bucket`
- cyclic `sin/cos` encodings

Categorical context is expanded with the fixed `contracts/categorical_feature_map.csv`.

## 4. Feature Alignment

Before model scoring, features are aligned to the exact model metadata lists:

- anomaly: `models/anomaly/baseline_model_metadata.json`
- risk: `models/risk/risk_model_metadata.json`
- leadtime: `models/leadtime/leadtime_bucket_model_promoted_metadata.json`

Missing model features are filled from `contracts/imputation_values.csv` when available. Otherwise the default fill is `0.0`.

## 5. Model Scoring

Scoring order:

1. `standard_scaler.joblib`
2. `isolation_forest.joblib`
3. `lightgbm_risk_model.joblib`
4. risk group calibration from `risk_model_group_calibration.json`
5. `lightgbm_leadtime_bucket_model_promoted.joblib`
6. priority scoring from `priority_engine_tuned_metadata.json`

Anomaly score uses the same training-time formula:

```text
anomaly_score = -isolation_forest.score_samples(scaled_features)
```

## 6. Operational Difference From Training

The leadtime model was trained on historical pre-fault rows. In live inference the package scores leadtime for incoming rows after risk scoring, using asset history for lag/rolling timeflow features when `fault_event_id` is not available.

This makes the package usable in production, but downstream users should interpret leadtime as a risk-context bucket estimate, not a guaranteed time-to-failure forecast.
