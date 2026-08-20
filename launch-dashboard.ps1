$ErrorActionPreference = "Stop"

$BaseUrl = "http://127.0.0.1:5150"
$Port = 5150
$Python = Join-Path $env:LOCALAPPDATA "Programs\Python\Python311\python.exe"
$AppDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$TokenFile = Join-Path $AppDir ".dashboard_token"

function Test-DashboardPort {
    $listener = Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    return $null -ne $listener
}

Write-Host ""
Write-Host " AI Command Center v2"
Write-Host " $BaseUrl"
Write-Host ""

if (-not (Test-DashboardPort)) {
    Start-Process -FilePath $Python -ArgumentList "app.py" -WorkingDirectory $AppDir -WindowStyle Hidden
}

$ready = $false
for ($i = 0; $i -lt 20; $i++) {
    if (Test-DashboardPort) {
        $ready = $true
        break
    }
    Start-Sleep -Milliseconds 250
}

# The app writes .dashboard_token on startup, close enough after the port
# opens that a couple of extra short waits cover it comfortably.
$Token = $null
for ($i = 0; $i -lt 8; $i++) {
    if (Test-Path $TokenFile) {
        $Token = (Get-Content $TokenFile -Raw).Trim()
        if ($Token) { break }
    }
    Start-Sleep -Milliseconds 250
}

if ($Token) {
    Start-Process ("$BaseUrl/?token=$Token")
}
else {
    Write-Host " Could not read .dashboard_token, opening without it; action buttons will need a manual token."
    Start-Process $BaseUrl
}

if ($ready) {
    Write-Host " Dashboard opened."
}
else {
    Write-Host " Dashboard tab opened. If it is still loading, refresh the tab in a moment."
}
