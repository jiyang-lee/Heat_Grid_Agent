param(
    [string]$ApiBase = "http://127.0.0.1:8003",
    [string]$ImportedBy = "local-replay-setup"
)

$ErrorActionPreference = "Stop"
$payload = @{
    package_path = "/var/lib/heatgrid/incoming/demo_replay.zip"
    imported_by  = $ImportedBy
} | ConvertTo-Json

$result = Invoke-RestMethod `
    -Uri "$ApiBase/api/replay-datasets/import" `
    -Method Post `
    -ContentType "application/json" `
    -Body $payload

$result | ConvertTo-Json -Depth 10
