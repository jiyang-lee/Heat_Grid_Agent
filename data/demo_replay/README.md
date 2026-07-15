# PreDist synthetic replay data

`config/sensor_manifest.csv` is the tracked sensor selection. Exactly four physical raw
sensors must have `enabled=true`. The generator rebuilds the model sensor registry from
the raw schema and deployed model metadata, so changing the four sensors does not require
a backend or database schema change.

Small validation run:

```powershell
.\.venv\Scripts\python.exe scripts\generate_synthetic_replay.py --sample --stations 1-31 --output "$env:TEMP\heatgrid-replay-sample" --overwrite --run-inference-validation
```

Full three-year generation (large output, intentionally not tracked). The default v2
profile creates 96 candidates from continuous source fault trajectories, distributes
them across configuration-compatible substations, and requires at least 10
model-approved fault scenarios before validation passes:

```powershell
.\.venv\Scripts\python.exe scripts\generate_synthetic_replay.py --full-range --overwrite
```

Validate an existing output:

```powershell
.\.venv\Scripts\python.exe scripts\generate_synthetic_replay.py --validate-only --run-inference-validation --output data\demo_replay\current
```

The output root contains `dataset_manifest.json`, copied sensor/registry manifests,
scenario and approved seek-point manifests, fallback donor provenance, monthly `raw/`
shards, monthly `windows/` shards, and `validation_report.json`. Generated files under
`data/demo_replay/current/` are ignored by Git.
