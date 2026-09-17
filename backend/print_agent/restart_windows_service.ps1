$ErrorActionPreference = "Stop"

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
$isAdmin = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    $arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
    Start-Process -FilePath "powershell.exe" -ArgumentList $arguments -Verb RunAs
    exit
}

Restart-Service -Name "HedePrintAgent" -Force
(Get-Service -Name "HedePrintAgent").WaitForStatus("Running", [TimeSpan]::FromSeconds(30))
Write-Host "Hede Label Print Service has restarted." -ForegroundColor Green
