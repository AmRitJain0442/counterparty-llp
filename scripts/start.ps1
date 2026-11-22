param([int]$Port = 8080)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$cfg = Join-Path $env:LOCALAPPDATA 'CounterpartyLLP'
$stored = Join-Path $cfg 'crustdata.dpapi'
if (!$env:CRUSTDATA_API_KEY -and (Test-Path $stored)) {
    $encrypted = Get-Content -LiteralPath $stored | ConvertTo-SecureString
    $env:CRUSTDATA_API_KEY = [System.Net.NetworkCredential]::new('', $encrypted).Password
}
$watch = Join-Path $cfg 'watch-id'
if (!$env:CRUSTDATA_WATCH_ID -and (Test-Path $watch)) {
    $env:CRUSTDATA_WATCH_ID = (Get-Content -LiteralPath $watch -Raw).Trim()
}
$pointer = Join-Path $cfg 'adc-path'
if (!$env:GOOGLE_APPLICATION_CREDENTIALS -and (Test-Path $pointer)) {
    $env:GOOGLE_APPLICATION_CREDENTIALS = (Get-Content -LiteralPath $pointer -Raw).Trim()
}
if (!$env:GOOGLE_CLOUD_PROJECT -and $env:GOOGLE_APPLICATION_CREDENTIALS) {
    $env:GOOGLE_CLOUD_PROJECT = (Get-Content $env:GOOGLE_APPLICATION_CREDENTIALS -Raw | ConvertFrom-Json).project_id
}
if (!$env:GOOGLE_CLOUD_LOCATION) { $env:GOOGLE_CLOUD_LOCATION = 'global' }
& .\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port $Port
exit $LASTEXITCODE
