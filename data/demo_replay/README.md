# PreDist synthetic replay data

`config/sensor_manifest.csv` is the tracked sensor selection. Exactly four physical raw
sensors must have `enabled=true`. The generator rebuilds the model sensor registry from
the raw schema and deployed model metadata, so changing the four sensors does not require
a backend or database schema change.

Small validation run:

```powershell
.\.venv\Scripts\python.exe scripts\generate_synthetic_replay.py --sample --stations 1-31 --output "$env:TEMP\heatgrid-replay-sample" --overwrite --run-inference-validation
```

Full three-year generation (large output, intentionally not tracked). The default v3
profile creates 96 interleaved high/medium candidates from continuous source fault
trajectories, adds a 24-hour recovery phase, and decorrelates normal donor timing across
substations. Validation requires at least 20 model-approved high scenarios and 20
model-approved medium scenarios:

```powershell
.\.venv\Scripts\python.exe scripts\generate_synthetic_replay.py --full-range --overwrite
```

Validate an existing output:

```powershell
.\.venv\Scripts\python.exe scripts\generate_synthetic_replay.py --validate-only --run-inference-validation --output data\demo_replay\current
```

The output root contains `dataset_manifest.json`, copied sensor/registry manifests,
scenario and approved seek-point manifests (including fleet-level preset counts),
fallback donor provenance, monthly `raw/`
shards, monthly `windows/` shards, and `validation_report.json`. Generated files under
`data/demo_replay/current/` are ignored by Git.
