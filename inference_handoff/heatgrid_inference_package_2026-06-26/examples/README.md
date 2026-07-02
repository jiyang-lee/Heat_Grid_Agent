# Examples

Score a window-feature CSV:

```powershell
python ..\run_inference.py score-windowed `
  --input C:\Project3\HeatGrid_Agent\data\processed\ml_features\trainable_windows.csv `
  --output .\scores_from_windowed.csv
```

Score one raw operational file:

```powershell
python ..\run_inference.py score-raw-file `
  --input "C:\Project3\HeatGrid_Agent\data\raw_data\predist_v2\manufacturer 1\operational_data\substation_1.csv" `
  --raw-root "C:\Project3\HeatGrid_Agent\data\raw_data\predist_v2" `
  --output .\scores_from_raw_file.csv
```

Score every raw operational file under a root:

```powershell
python ..\run_inference.py score-raw-root `
  --raw-root "C:\Project3\HeatGrid_Agent\data\raw_data\predist_v2" `
  --output .\scores_from_raw_root.csv
```
