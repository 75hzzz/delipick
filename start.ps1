param([switch]$Demo)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (!(Get-Command docker -ErrorAction SilentlyContinue)) {
    foreach ($bin in @("$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin", "$env:ProgramFiles\Docker\Docker\resources\bin")) {
        if (Test-Path -LiteralPath (Join-Path $bin 'docker.exe')) { $env:PATH = "$bin;$env:PATH"; break }
    }
}
docker info --format '{{.ServerVersion}}'
if ($LASTEXITCODE -ne 0) { throw 'Start Docker Desktop first.' }
if (!(Test-Path -LiteralPath '.env')) {
    $template = [IO.File]::ReadAllText((Join-Path $PSScriptRoot '.env.example'))
    $template = $template.Replace('CHANGE_ME_APP_PASSWORD', [Guid]::NewGuid().ToString('N'))
    $template = $template.Replace('CHANGE_ME_ROOT_PASSWORD', [Guid]::NewGuid().ToString('N'))
    [IO.File]::WriteAllText((Join-Path $PSScriptRoot '.env'), $template, (New-Object Text.UTF8Encoding($false)))
}
$overrides = @{}
if ($Demo) {
    $overrides = @{COMPOSE_PROJECT_NAME='delipick-integrated-demo'; DATASET_MODE='demo'; DB_NAME='delipick_demo';
                   QDRANT_COLLECTION='delipick_demo'; API_PORT='18087'; MYSQL_PORT='13308'; QDRANT_PORT='16340';
                   ENABLE_DELIVERY_WORKER='false'}
}
$previous = @{}
try {
    foreach ($key in $overrides.Keys) {
        $previous[$key] = [Environment]::GetEnvironmentVariable($key, 'Process')
        [Environment]::SetEnvironmentVariable($key, $overrides[$key], 'Process')
    }
    $config = docker compose config --format json | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0) { throw 'Invalid Compose configuration.' }
    if ($config.services.init.environment.DATASET_MODE -eq 'existing' -and !(Test-Path -LiteralPath 'delipick_server/database/database.sql' -PathType Leaf)) {
        Write-Warning 'No SQL dump found. A fresh database needs database/database.sql; a recognized initialized volume can be reused.'
    }
    docker compose up -d --build --wait --wait-timeout 300
    if ($LASTEXITCODE -ne 0) { throw 'Startup failed. Inspect: docker compose logs import init api' }
    docker compose ps -a
    $port = $config.services.api.ports[0].published
    $qport = $config.services.qdrant.ports[0].published
    Write-Host "API: http://localhost:$port/docs"
    Write-Host "Qdrant: http://localhost:$qport/dashboard"
} finally {
    foreach ($key in $previous.Keys) { [Environment]::SetEnvironmentVariable($key, $previous[$key], 'Process') }
}
