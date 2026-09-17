$ErrorActionPreference = "Stop"

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
$isAdmin = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    $arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
    Start-Process -FilePath "powershell.exe" -ArgumentList $arguments -Verb RunAs
    exit
}

$serviceName = "HedePrintAgent"
$displayName = "Hede Label Print Service"
$description = "Receives Hede shoe label jobs and sends them to the local TSC printer."
$installDirectory = Join-Path $env:ProgramFiles "Hede\PrintAgent"
$dataDirectory = Join-Path $env:ProgramData "HedePrintAgent"
$packageDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$sourceExecutable = Join-Path $packageDirectory "HedePrintAgent.exe"
$sourceConfig = Join-Path $packageDirectory "HedePrintAgent.config.json"
$targetExecutable = Join-Path $installDirectory "HedePrintAgent.exe"
$targetConfig = Join-Path $dataDirectory "config.json"
$binaryPath = '"{0}" --service' -f $targetExecutable

if (-not (Test-Path -LiteralPath $sourceExecutable)) {
    throw "HedePrintAgent.exe is missing from the installation package."
}
if (-not (Test-Path -LiteralPath $sourceConfig)) {
    throw "HedePrintAgent.config.json is missing from the installation package."
}

Write-Host "Installing $displayName..." -ForegroundColor Cyan
$existingService = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
if ($existingService -and $existingService.Status -ne "Stopped") {
    Stop-Service -Name $serviceName -Force
    $existingService.WaitForStatus("Stopped", [TimeSpan]::FromSeconds(30))
}

New-Item -ItemType Directory -Path $installDirectory -Force | Out-Null
New-Item -ItemType Directory -Path $dataDirectory -Force | Out-Null
Copy-Item -LiteralPath $sourceExecutable -Destination $targetExecutable -Force
if (-not (Test-Path -LiteralPath $targetConfig)) {
    Copy-Item -LiteralPath $sourceConfig -Destination $targetConfig
    Write-Host "Created configuration: $targetConfig"
} else {
    Write-Host "Preserved existing configuration: $targetConfig"
}

if ($existingService) {
    & sc.exe config $serviceName binPath= $binaryPath start= auto depend= Spooler DisplayName= $displayName | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Failed to update the Windows service." }
} else {
    New-Service `
        -Name $serviceName `
        -BinaryPathName $binaryPath `
        -DisplayName $displayName `
        -Description $description `
        -StartupType Automatic `
        -DependsOn Spooler | Out-Null
}

& sc.exe description $serviceName $description | Out-Null
& sc.exe failure $serviceName reset= 86400 actions= restart/5000/restart/15000/restart/60000 | Out-Null
& sc.exe failureflag $serviceName 1 | Out-Null
Start-Service -Name $serviceName
(Get-Service -Name $serviceName).WaitForStatus("Running", [TimeSpan]::FromSeconds(30))

Write-Host ""
Write-Host "$displayName is installed and running." -ForegroundColor Green
Write-Host "Startup: Automatic"
Write-Host "Configuration: $targetConfig"
Write-Host "Logs: $(Join-Path $dataDirectory 'logs')"
Write-Host "Health check: http://127.0.0.1:18120/health"
