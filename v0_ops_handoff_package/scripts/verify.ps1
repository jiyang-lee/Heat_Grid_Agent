$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

docker compose up -d

$Ready = $false
for ($i = 0; $i -lt 30; $i++) {
    docker compose exec -T postgres psql -U heatgrid -d heatgrid_ops -c "select 1" *> $null
    if ($LASTEXITCODE -eq 0) {
        $Ready = $true
        break
    }
    Start-Sleep -Seconds 1
}

if (-not $Ready) {
    docker compose logs postgres
    throw "Postgres did not become query-ready"
}

docker compose exec -T postgres psql -U heatgrid -d heatgrid_ops -f /handoff/queries/verify.sql

$Payload = Get-Content -Raw -Encoding UTF8 "input.json" | ConvertFrom-Json
$Raw = $Payload.raw_context
$Priority = $Payload.priority_context
$Calculation = $Priority.priority.calculation
$Explanation = $Priority.explanation

if ($Raw.current_best_sensor_values.top_n -ne 10) {
    throw "current_best_sensor_values.top_n must be 10"
}
if ($Raw.current_best_sensor_values.values.Count -ne 10) {
    throw "current_best_sensor_values.values count must be 10"
}
if ($Raw.m1_specialist_features.feature_count -ne 13) {
    throw "m1_specialist_features.feature_count must be 13"
}
if ($Raw.m1_specialist_features.features.Count -ne 13) {
    throw "m1_specialist_features.features count must be 13"
}
if ($null -ne $Priority.formula) {
    throw "priority_context.formula must not exist"
}
if ($null -ne $Priority.review_reasons) {
    throw "priority_context.review_reasons must not exist"
}
if ($null -ne $Priority.card.review_required) {
    throw "priority_context.card.review_required must not exist"
}
if ($Calculation.current_best_weight -ne 0.65) {
    throw "current_best_weight must be 0.65"
}
if ($Calculation.m1_specialist_weight -ne 0.35) {
    throw "m1_specialist_weight must be 0.35"
}
if ($null -ne $Calculation.current_best_priority_score) {
    throw "calculation.current_best_priority_score must not exist"
}
if ($null -ne $Calculation.m1_specialist_priority_score) {
    throw "calculation.m1_specialist_priority_score must not exist"
}
if ($Explanation.review_required -ne $true) {
    throw "explanation.review_required must be true"
}
if ($Explanation.review_reasons.Count -ne 3) {
    throw "explanation.review_reasons count must be 3"
}

Write-Host "input.json OK: current-best=10, m1=13, weights=0.65/0.35"
