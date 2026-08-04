param(
    [string]$Container = "heatgrid-pgvector"
)

$ErrorActionPreference = "Stop"
$dump = Join-Path $PSScriptRoot "database_data.dump"

if (-not (Test-Path -LiteralPath $dump)) {
    throw "database_data.dump를 찾을 수 없습니다: $dump"
}

$running = docker inspect -f '{{.State.Running}}' $Container 2>$null
if ($LASTEXITCODE -ne 0 -or $running.Trim() -ne "true") {
    throw "$Container 컨테이너가 실행 중이 아닙니다. 먼저 docker compose up -d --build heatgrid-backend를 실행하세요."
}

$remoteDump = "/tmp/heatgrid_database_data.dump"
docker cp "$dump" "${Container}:$remoteDump"
if ($LASTEXITCODE -ne 0) { throw "dump 파일을 컨테이너로 복사하지 못했습니다." }

$truncateSql = @'
DO $$
DECLARE r record;
BEGIN
  FOR r IN
    SELECT tablename
    FROM pg_tables
    WHERE schemaname = 'public'
      AND tablename NOT IN ('schema_migrations', 'checkpoint_migrations')
  LOOP
    EXECUTE format('TRUNCATE TABLE public.%I CASCADE', r.tablename);
  END LOOP;
END $$;
'@
$truncateSql | docker exec -i $Container psql -U heatgrid_migrator -d heatgrid_ops
if ($LASTEXITCODE -ne 0) { throw "기존 PostgreSQL 데이터를 초기화하지 못했습니다." }

docker exec $Container pg_restore -U heatgrid_migrator -d heatgrid_ops --data-only --disable-triggers --no-owner --no-privileges --exit-on-error $remoteDump
if ($LASTEXITCODE -ne 0) { throw "PostgreSQL 데이터 복원에 실패했습니다." }

docker exec $Container rm -f $remoteDump
Write-Host "PostgreSQL 데이터 복원이 완료되었습니다."
