# HeatGrid Inference Handoff

This folder is the deployable inference package for the current HeatGrid ML flow.
It contains the final trained model files, model metadata, feature contracts, raw-to-window feature engineering code, and a CLI for scoring.

## What This Package Contains

```text
models/
  anomaly/
    standard_scaler.joblib
    isolation_forest.joblib
    baseline_model_metadata.json
    anomaly_baseline_thresholds.csv
  risk/
    lightgbm_risk_model.joblib
    risk_model_metadata.json
    risk_model_group_calibration.json
  leadtime/
    lightgbm_leadtime_bucket_model_promoted.joblib
    leadtime_bucket_model_promoted_metadata.json
  priority/
    priority_engine_tuned_metadata.json
contracts/
  feature_columns.csv
  metadata_columns.csv
  imputation_values.csv
  categorical_feature_map.csv
  agent_feature_contract.json
docs/
  agent_preprocessed_input_columns.md
  agent_full_data_contract.md
src/
  heatgrid_inference/
run_inference.py
```

## Runtime Flow

```text
raw operational telemetry
  -> 6 hour windowing
  -> sensor statistics / missingness / time context / categorical one-hot
  -> imputation and model feature ordering
  -> anomaly score
  -> risk probability and calibrated risk level
  -> leadtime bucket
  -> priority score and priority level
```

## Install Requirements

Use the target project's Python environment and install the dependencies from this folder:

```powershell
pip install -e .
```

Or run directly from this folder without installation:

```powershell
python run_inference.py --help
```

## Score Existing Window Feature CSV

Use this when the target system already creates rows shaped like `trainable_windows.csv`.

```powershell
python run_inference.py score-windowed `
  --input C:\path\to\trainable_windows_like.csv `
  --output C:\path\to\heatgrid_scores.csv
```

## Score One Raw Operational CSV

Use this when one substation raw file is available.
Pass `--raw-root` when configuration and event history CSVs are available under a `predist_v2`-style directory.

```powershell
python run_inference.py score-raw-file `
  --input "C:\path\to\predist_v2\manufacturer 1\operational_data\substation_1.csv" `
  --raw-root "C:\path\to\predist_v2" `
  --output C:\path\to\substation_1_scores.csv
```

If the path does not contain `manufacturer N` or the file name does not match `substation_N.csv`, pass explicit metadata:

```powershell
python run_inference.py score-raw-file `
  --input C:\path\to\operational.csv `
  --manufacturer "manufacturer 1" `
  --substation-id 1 `
  --output C:\path\to\scores.csv
```

## Score A Full Raw Root

```powershell
python run_inference.py score-raw-root `
  --raw-root "C:\path\to\predist_v2" `
  --output C:\path\to\heatgrid_scores.csv
```

## Input Assumptions

Raw operational CSVs are expected to use semicolon delimiters and include a `timestamp` column.
The feature engineering code supports the 29 required raw columns documented in `docs/agent_preprocessed_input_columns.md`.
Missing raw columns are allowed, but their derived model features will be imputed from the training contract.

For best risk calibration, provide the context files under the raw root:

- `manufacturer */configuration_types.csv`
- `manufacturer */faults.csv`
- `manufacturer */disturbances.csv`

Without event history, the service uses the sentinel value `9999.0` for days-since-event features.

## Output

The output CSV contains one row per substation and 6 hour window, including:

- `anomaly_score`, `anomaly_label`
- `risk_probability`, `risk_level_calibrated`
- `predicted_lead_time_bucket`, `predicted_lead_time_confidence`
- `priority_score`, `priority_level`, `priority_reason`

## Important Notes

- This is an inference package, not a retraining package.
- The model files under `models/` are the trained artifacts used by the current project.
- The priority engine is rule based and uses `models/priority/priority_engine_tuned_metadata.json`.
- For retraining, the target team needs the original preprocessing notebooks/scripts, raw data, split policy, experiment logs, and promotion criteria from the full repository.
