# HeatGrid Agent

HeatGrid Agent is an ML workflow for turning district-heating substation telemetry into anomaly, risk, lead-time, and service-priority signals.

The repository contains the research/preprocessing workflow, trained model artifacts, reports, and a separate inference handoff package that can be given to another project for integration.

## Current Status

The final handoff models are available under:

```text
model_handoff/heatgrid_ml_models_2026-06-25/
```

The deployment-oriented inference package is available under:

```text
inference_handoff/heatgrid_inference_package_2026-06-26/
```

Use `model_handoff` only when the target project already has matching preprocessing and feature-engineering logic.
Use `inference_handoff` when the target project needs raw/windowed data scoring code as well.

## Main Workflow

```text
raw operational telemetry
  -> label/context alignment
  -> 6 hour window preprocessing
  -> feature selection and imputation contract
  -> anomaly model
  -> risk model and group calibration
  -> leadtime model
  -> priority scoring engine
```

## Repository Layout

```text
data/
  raw_data/                  Raw Predist/XAI4Heat source data
  processed/                 Generated preprocessing/model outputs
PREPROCESSING/
  osj/                       Main notebook and script workflow
  docs/                      ML process notes and contracts
model_handoff/
  heatgrid_ml_models_2026-06-25/
                              Final model-only handoff package
inference_handoff/
  heatgrid_inference_package_2026-06-26/
                              Integration package with models, contracts, and inference code
report/
  experiment_comparison/     Experiment summaries and comparison outputs
diary/
  project notes and handoff logs
```

## Environment

This project uses Python 3.12 and `uv`.

```powershell
uv sync
```

If using plain pip for the inference package only:

```powershell
cd inference_handoff/heatgrid_inference_package_2026-06-26
pip install -e .
```

## Official Pipeline Scripts

The current official pipeline scripts are:

```powershell
python PREPROCESSING/osj/pipeline_scripts/06_risk_calibration.py
python PREPROCESSING/osj/pipeline_scripts/06_leadtime_model.py
python PREPROCESSING/osj/pipeline_scripts/07_priority_engine.py
```

These scripts consume generated files under `data/processed/` and update the official risk, leadtime, and priority outputs.

## Model Handoff

`model_handoff/heatgrid_ml_models_2026-06-25/` contains the final trained model files and metadata:

```text
anomaly/
  standard_scaler.joblib
  isolation_forest.joblib
  baseline_model_metadata.json
risk/
  lightgbm_risk_model.joblib
  risk_model_group_calibration.json
  risk_model_metadata.json
leadtime/
  lightgbm_leadtime_bucket_model_promoted.joblib
  leadtime_bucket_model_promoted_metadata.json
priority/
  priority_engine_tuned_metadata.json
docs/
  agent_preprocessed_input_columns.md
  agent_full_data_contract.md
MANIFEST.json
```

The joblib files in this folder were verified against the current project-generated artifacts by SHA256 hash.

## Inference Handoff

`inference_handoff/heatgrid_inference_package_2026-06-26/` is the package to give to another project when it needs to run inference from real incoming data.

It includes:

- final model artifacts
- feature contracts and imputation values
- categorical one-hot mapping
- raw telemetry to 6 hour window feature engineering
- anomaly, risk, leadtime, and priority scoring code
- CLI entrypoint
- package manifest with SHA256 hashes

Run help:

```powershell
python inference_handoff/heatgrid_inference_package_2026-06-26/run_inference.py --help
```

Score a raw operational file:

```powershell
python inference_handoff/heatgrid_inference_package_2026-06-26/run_inference.py score-raw-file `
  --input "data/raw_data/predist_v2/manufacturer 1/operational_data/substation_1.csv" `
  --raw-root "data/raw_data/predist_v2" `
  --output "scores.csv"
```

Score an existing window-feature CSV:

```powershell
python inference_handoff/heatgrid_inference_package_2026-06-26/run_inference.py score-windowed `
  --input "data/processed/ml_features/trainable_windows.csv" `
  --output "scores.csv"
```

## Retraining Scope

The inference package is not enough for retraining.

For retraining or audit reproduction, provide the full repository plus the required raw/processed data and experiment history. The target team needs:

- raw data
- label alignment logic
- window preprocessing logic
- feature selection and imputation contract generation
- train/validation/holdout split policy
- training scripts or notebooks
- experiment comparison outputs
- model promotion notes

The split between inference integration and retraining is documented in:

```text
inference_handoff/heatgrid_inference_package_2026-06-26/docs/retraining_scope.md
```

## Verification Commands

Compile the inference package:

```powershell
python -m compileall inference_handoff/heatgrid_inference_package_2026-06-26/src
```

Smoke test raw scoring:

```powershell
python inference_handoff/heatgrid_inference_package_2026-06-26/run_inference.py score-raw-file `
  --input "data/raw_data/predist_v2/manufacturer 1/operational_data/substation_1.csv" `
  --raw-root "data/raw_data/predist_v2" `
  --output "inference_handoff/heatgrid_inference_package_2026-06-26/examples/scores_from_raw_file_smoke.csv"
```

Smoke test windowed scoring:

```powershell
python inference_handoff/heatgrid_inference_package_2026-06-26/run_inference.py score-windowed `
  --input "data/processed/ml_features/trainable_windows.csv" `
  --output "inference_handoff/heatgrid_inference_package_2026-06-26/examples/scores_from_windowed_smoke.csv"
```

Remove smoke-test CSVs before external delivery if they are generated.

## Notes

- `report/` and `PREPROCESSING/osj/experiments/06_test/` are for analysis and experiment comparison, not minimal deployment.
- `data/processed/` contains generated artifacts and can be large.
- Priority scoring is rule based and uses `priority_engine_tuned_metadata.json`; it is not a joblib model.
