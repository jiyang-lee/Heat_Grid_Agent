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

Push-Location $projectRoot
try {
    docker compose up -d --build --wait
    if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL/백엔드 Docker 실행에 실패했습니다.' }
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
