$ErrorActionPreference = "Stop"
$projectRoot = "E:\hede"
$frontendRoot = Join-Path $projectRoot "frontend"
$outputRoot = Join-Path $projectRoot "outputs\product-card-copy-deploy-20261026"
$buildPath = [IO.Path]::GetFullPath((Join-Path $frontendRoot ".next"))
$backupPath = [IO.Path]::GetFullPath((Join-Path $outputRoot "previous-next"))
$failedPath = [IO.Path]::GetFullPath((Join-Path $outputRoot "failed-next"))
$nodePath = "D:\nodejs\node.exe"
$nextEntry = Join-Path $frontendRoot "node_modules\next\dist\bin\next"
$resultPath = Join-Path $outputRoot "result.json"
$previousBuildId = (Get-Content -LiteralPath (Join-Path $buildPath "BUILD_ID") -Raw).Trim()

if ($buildPath -ne "E:\hede\frontend\.next" -or
    -not $backupPath.StartsWith($outputRoot + "\", [StringComparison]::OrdinalIgnoreCase) -or
    -not $failedPath.StartsWith($outputRoot + "\", [StringComparison]::OrdinalIgnoreCase)) {
    throw "Build paths are outside the intended deployment directories"
}
if ((Test-Path -LiteralPath $backupPath) -or (Test-Path -LiteralPath $failedPath) -or
    (Test-Path -LiteralPath $resultPath)) {
    throw "Deployment already started; refusing to overwrite its backup"
}
$listeners = @(Get-NetTCPConnection -LocalPort 3001 -State Listen)
$owners = @($listeners.OwningProcess | Sort-Object -Unique)
if ($owners.Count -ne 1) { throw "Expected a single frontend process on port 3001" }
$frontendProcessId = $owners[0]
$process = Get-CimInstance Win32_Process -Filter "ProcessId = $frontendProcessId"
if ($process.Name -ne "node.exe" -or
    $process.CommandLine -notmatch 'E:\\hede\\frontend\\' -or
    $process.CommandLine -notmatch 'start -H 0\.0\.0\.0 -p 3001') {
    throw "Port 3001 does not belong to the expected production frontend"
}

function Start-Frontend {
    $server = Start-Process -FilePath $nodePath -ArgumentList @($nextEntry, "start", "-H", "0.0.0.0", "-p", "3001") `
        -WorkingDirectory $frontendRoot -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $outputRoot "frontend.stdout.log") `
        -RedirectStandardError (Join-Path $outputRoot "frontend.stderr.log")
    for ($attempt = 0; $attempt -lt 40; $attempt++) {
        Start-Sleep -Seconds 1
        $server.Refresh()
        if ($server.HasExited) { throw "Frontend exited before becoming ready" }
        try {
            $response = Invoke-WebRequest -Uri "http://127.0.0.1:3001/products" -UseBasicParsing -TimeoutSec 3
            if ($response.StatusCode -eq 200) { return $server.Id }
        } catch {
            if ($attempt -eq 39) { throw }
        }
    }
    throw "Frontend did not become ready"
}

$result = @{ status = "building"; started_at = (Get-Date).ToString("o"); backend_restarted = $false;
    previous_process_id = $frontendProcessId; previous_build_id = $previousBuildId }
$result | ConvertTo-Json | Set-Content -LiteralPath $resultPath -Encoding UTF8
Stop-Process -Id $frontendProcessId
Wait-Process -Id $frontendProcessId -Timeout 15 -ErrorAction SilentlyContinue
Move-Item -LiteralPath $buildPath -Destination $backupPath

try {
    Push-Location $frontendRoot
    try {
        & $nodePath $nextEntry build *> (Join-Path $outputRoot "build.log")
        if ($LASTEXITCODE -ne 0) { throw "Production build failed; see build.log" }
    } finally {
        Pop-Location
    }
    $newBuildId = (Get-Content -LiteralPath (Join-Path $buildPath "BUILD_ID") -Raw).Trim()
    if ($newBuildId -eq $previousBuildId) { throw "Production build ID did not change" }
    $result.process_id = Start-Frontend
    $result.build_id = $newBuildId
    $result.status = "completed"
    $result.completed_at = (Get-Date).ToString("o")
} catch {
    $result.error = $_.Exception.Message
    $active = @(Get-NetTCPConnection -LocalPort 3001 -State Listen -ErrorAction SilentlyContinue)
    if ($active.Count -eq 0) {
        if (Test-Path -LiteralPath $buildPath) { Move-Item -LiteralPath $buildPath -Destination $failedPath }
        Move-Item -LiteralPath $backupPath -Destination $buildPath
        $result.rollback_process_id = Start-Frontend
        $result.status = "rolled_back"
    } else {
        $result.status = "needs_review"
    }
    throw
} finally {
    $result | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $resultPath -Encoding UTF8
}
$result | ConvertTo-Json -Depth 4
