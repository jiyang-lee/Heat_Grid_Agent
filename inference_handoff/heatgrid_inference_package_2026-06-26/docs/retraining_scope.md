# Retraining Scope

This package is sufficient for inference integration.

It is not sufficient for full retraining or audit reproduction.

## Included

- Final trained joblib models
- Model metadata
- Feature contracts
- Imputation values
- Raw-to-window feature engineering code
- Inference scoring code
- Priority rule metadata

## Not Included

- Full raw dataset
- Label alignment notebooks
- Train/validation/holdout generation notebooks
- Experiment scripts and tuning grids
- Report notebooks
- Model promotion audit history

## When Full Repository Is Needed

Send the full project, or a separate retraining package, when the receiving team needs to:

- regenerate labels
- rebuild `trainable_windows.csv`
- retrain anomaly/risk/leadtime models
- compare experiments
- audit data leakage or split policy
- reproduce paper/report metrics
