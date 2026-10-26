$ErrorActionPreference = "Stop"
$frontendRoot = "E:\hede\frontend"
$outputRoot = "E:\hede\outputs\product-card-copy-deploy-20261026"
$nodePath = "D:\nodejs\node.exe"
$nextEntry = Join-Path $frontendRoot "node_modules\next\dist\bin\next"
$releaseDirectory = ".next-product-copy-20261026"
$releasePath = Join-Path $frontendRoot $releaseDirectory
$resultPath = Join-Path $outputRoot "activation.json"
$releaseId = (Get-Content -LiteralPath (Join-Path $releasePath "BUILD_ID") -Raw).Trim()
$previousBuildId = (Get-Content -LiteralPath (Join-Path $frontendRoot ".next\BUILD_ID") -Raw).Trim()
$previousDist = $env:NEXT_DIST_DIR
$oldStopped = $false
$previewProcess = $null
$newProcess = $null

function Start-Release($port, $logPrefix) {
    $server = Start-Process -FilePath $nodePath -ArgumentList @($nextEntry, "start", "-H", "0.0.0.0", "-p", $port) `
        -WorkingDirectory $frontendRoot -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $outputRoot "$logPrefix.stdout.log") `
        -RedirectStandardError (Join-Path $outputRoot "$logPrefix.stderr.log")
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        Start-Sleep -Seconds 1
        $server.Refresh()
        if ($server.HasExited) { throw "Frontend exited before becoming ready on port $port" }
        try {
            $response = Invoke-WebRequest -Uri "http://127.0.0.1:$port/products" -UseBasicParsing -TimeoutSec 3
            if ($response.StatusCode -eq 200) { return $server }
        } catch {
            if ($attempt -eq 29) { throw }
        }
    }
    throw "Frontend startup timed out on port $port"
}

function Assert-PublishedFix($port) {
    $chunk = Get-ChildItem -LiteralPath (Join-Path $releasePath "static\chunks") -Filter "*.js" |
        Where-Object { (Get-Content -LiteralPath $_.FullName -Raw -Encoding UTF8).Contains("cursor-text flex-col gap-2 select-text") } |
        Select-Object -First 1
    if (-not $chunk) { throw "Cannot locate the corrected product card bundle" }
    $response = Invoke-WebRequest -Uri "http://127.0.0.1:$port/_next/static/chunks/$($chunk.Name)" -UseBasicParsing -TimeoutSec 10
    if ($response.StatusCode -ne 200 -or -not $response.Content.Contains("cursor-text flex-col gap-2 select-text")) {
        throw "The corrected product card bundle is not served by port $port"
    }
    return $chunk.Name
}

$result = @{ status = "validating"; started_at = (Get-Date).ToString("o"); build_id = $releaseId;
    previous_build_id = $previousBuildId; dist_dir = $releaseDirectory; backend_restarted = $false }
try {
    if (Get-NetTCPConnection -LocalPort 3002 -State Listen -ErrorAction SilentlyContinue) {
        throw "Preview port 3002 is occupied"
    }
    $env:NEXT_DIST_DIR = $releaseDirectory
    $previewProcess = Start-Release "3002" "preview"
    $result.verified_chunk = Assert-PublishedFix "3002"
    $owners = @((Get-NetTCPConnection -LocalPort 3001 -State Listen).OwningProcess | Sort-Object -Unique)
    if ($owners.Count -ne 1) { throw "Expected a single process on frontend port 3001" }
    $oldProcess = Get-CimInstance Win32_Process -Filter "ProcessId = $($owners[0])"
    if ($oldProcess.Name -ne "node.exe" -or $oldProcess.CommandLine -notmatch 'E:\\hede\\frontend\\' -or
        $oldProcess.CommandLine -notmatch 'start -H 0\.0\.0\.0 -p 3001') {
        throw "Frontend port is not owned by the expected project"
    }
    $result.previous_process_id = $owners[0]
    Stop-Process -Id $owners[0]
    $oldStopped = $true
    Wait-Process -Id $owners[0] -Timeout 15 -ErrorAction SilentlyContinue
    $newProcess = Start-Release "3001" "production"
    $result.process_id = $newProcess.Id
    $result.verified_chunk = Assert-PublishedFix "3001"
    $result.status = "completed"
    $result.completed_at = (Get-Date).ToString("o")
} catch {
    $result.error = $_.Exception.Message
    if ($oldStopped) {
        if ($newProcess) { Stop-Process -Id $newProcess.Id -ErrorAction SilentlyContinue }
        $env:NEXT_DIST_DIR = ".next"
        $rollbackProcess = Start-Release "3001" "rollback"
        $result.rollback_process_id = $rollbackProcess.Id
        $result.status = "rolled_back"
    } else {
        $result.status = "validation_failed"
    }
    throw
} finally {
    if ($previewProcess) { Stop-Process -Id $previewProcess.Id -ErrorAction SilentlyContinue }
    $env:NEXT_DIST_DIR = $previousDist
    $result | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $resultPath -Encoding UTF8
}
$result | ConvertTo-Json -Depth 4
