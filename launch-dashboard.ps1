$ErrorActionPreference = "Stop"

$Url = "http://127.0.0.1:5150"
$Port = 5150
$Python = Join-Path $env:LOCALAPPDATA "Programs\Python\Python311\python.exe"
$AppDir = Split-Path -Parent $MyInvocation.MyCommand.Path

function Test-DashboardPort {
    $listener = Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    return $null -ne $listener
}

Write-Host ""
Write-Host " AI Command Center v2"
Write-Host " $Url"
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

Start-Process $Url

if ($ready) {
    Write-Host " Dashboard opened."
}
else {
    Write-Host " Dashboard tab opened. If it is still loading, refresh the tab in a moment."
}
