$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$frontendRoot = Join-Path $projectRoot 'frontend'
$rootEnv = Join-Path $projectRoot '.env'
$rootEnvExample = Join-Path $projectRoot '.env.example'

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw 'Docker Desktop CLI를 찾을 수 없습니다.' }
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { throw 'Node.js/npm을 찾을 수 없습니다.' }

if (-not (Test-Path -LiteralPath $rootEnv)) {
    Copy-Item $rootEnvExample $rootEnv
    Write-Warning '.env를 만들었습니다. LLM 기능을 사용하려면 OPENAI_API_KEY를 입력하세요.'
}

$composeFiles = @('docker-compose.yml', 'docker-compose.local.yml', 'docker-compose.override.yml') |
    Where-Object { Test-Path -LiteralPath (Join-Path $projectRoot $_) }
$composeArgs = $composeFiles | ForEach-Object { '-f', $_ }

Push-Location $projectRoot
try {
    docker compose @composeArgs up -d --build --wait
    if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL/백엔드 Docker 실행에 실패했습니다.' }

    Write-Host '재생(고장 시나리오) 데이터셋 확인 중...'
    $datasets = @()
    try { $datasets = @(Invoke-RestMethod -Uri 'http://127.0.0.1:8003/api/replay-datasets' -Method Get) } catch {}
    $available = @($datasets | Where-Object { $_.status -eq 'available' -or $_.status -eq 'imported' })
    if ($available.Count -eq 0) {
        $backendContainer = (docker compose @composeArgs ps -q heatgrid-backend).Trim()
        $incomingListing = if ($backendContainer) { docker exec $backendContainer sh -c "ls /var/lib/heatgrid/incoming/*.zip 2>/dev/null" } else { $null }
        $zipPath = ($incomingListing -split "`n" | Where-Object { $_ -match 'demo_replay\.zip$' } | Select-Object -First 1)
        if (-not $zipPath) { $zipPath = ($incomingListing -split "`n" | Select-Object -First 1) }
        if ($zipPath) {
            Write-Host "재생 데이터셋을 임포트합니다: $zipPath"
            try {
                $body = @{ package_path = $zipPath.Trim(); imported_by = 'start-local' } | ConvertTo-Json
                Invoke-RestMethod -Uri 'http://127.0.0.1:8003/api/replay-datasets/import' -Method Post -ContentType 'application/json' -Body $body | Out-Null
                Write-Host '재생 데이터셋 임포트 완료.'
            }
            catch { Write-Warning "재생 데이터셋 임포트에 실패했습니다: $($_.Exception.Message)" }
        }
        else {
            Write-Warning '재생 데이터셋 zip을 찾지 못했습니다 (data\replay\ 아래에 있어야 합니다). git pull로 최신 데이터셋을 받았는지 확인 후 다시 실행하세요.'
        }
    }
    else {
        Write-Host "재생 데이터셋 $($available.Count)개 확인됨."
    }
}
finally { Pop-Location }

if (-not (Test-Path -LiteralPath (Join-Path $frontendRoot '.env'))) {
    Copy-Item (Join-Path $frontendRoot '.env.example') (Join-Path $frontendRoot '.env')
}

Start-Process powershell -WorkingDirectory $frontendRoot -ArgumentList @(
    '-NoExit', '-Command', 'npm ci; npm run dev -- --host 0.0.0.0 --port 5173'
)

$lanIp = Get-NetIPAddress -AddressFamily IPv4 -PrefixOrigin Dhcp -ErrorAction SilentlyContinue |
    Where-Object { $_.IPAddress -notlike '169.254.*' -and $_.IPAddress -ne '127.0.0.1' } |
    Select-Object -First 1 -ExpandProperty IPAddress

Write-Host 'PostgreSQL과 FastAPI가 Docker에서 실행 중입니다.'
Write-Host '프론트엔드 로컬 주소: http://127.0.0.1:5173'
if ($lanIp) { Write-Host "같은 네트워크 공유 주소: http://${lanIp}:5173" }
$isAdministrator = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if ($isAdministrator) {
    if (-not (Get-NetFirewallRule -DisplayName 'HeatGrid Frontend LAN (5173)' -ErrorAction SilentlyContinue)) {
        New-NetFirewallRule -DisplayName 'HeatGrid Frontend LAN (5173)' -Direction Inbound -Action Allow -Protocol TCP -LocalPort 5173 -Profile Any | Out-Null
    }
    Write-Host 'Windows 방화벽 TCP 5173 인바운드 규칙을 확인했습니다.'
}
else {
    Write-Warning '다른 PC 접속을 위해서는 PowerShell을 관리자 권한으로 한 번 실행해 TCP 5173 방화벽 규칙을 추가해야 합니다.'
}
