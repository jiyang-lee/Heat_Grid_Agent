# Artifact and model storage

The repository keeps source code, migrations, tests, and documentation. Generated
outputs, raw source PDFs, processed datasets, and trained model binaries are
local or external inputs and are intentionally not committed to Git.

Before running the full pipeline, restore these paths from the project's private
artifact store or regenerate them with the documented pipeline commands:

- `data/interim/` and `data/processed/`
- `data/rag_sources/raw/`
- `models/`
- `artifacts/`, `compare/`, and `output/`

Do not commit API keys, raw source packages, trained binaries, or generated CSV
reports. Keep a version manifest outside the repository that records the source
dataset revision, model revision, and pipeline commit used to produce a run.
