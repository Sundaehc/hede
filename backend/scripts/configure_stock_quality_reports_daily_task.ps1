[CmdletBinding(SupportsShouldProcess = $true)]
param([string]$UserId)

$ErrorActionPreference = 'Stop'
$taskName = 'HedeCheckStockQualityReportsDaily'
$backendRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).ProviderPath
$wrapperPath = Join-Path $backendRoot 'scripts\check_stock_quality_reports_daily.cmd'
foreach ($path in @($wrapperPath, (Join-Path $backendRoot '.venv\Scripts\python.exe'))) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Required file is missing: $path"
    }
}
if (-not $UserId) {
    $archiveTask = Get-ScheduledTask -TaskName 'HedeImportProductsDaily' -TaskPath '\'
    $UserId = $archiveTask.Principal.UserId
}
if (-not $UserId -or $UserId -in @('SYSTEM', 'S-1-5-18', 'LOCAL SERVICE', 'NETWORK SERVICE')) {
    throw 'Specify the interactive account that can read the report share.'
}

$chinaNow = [DateTimeOffset]::UtcNow.ToOffset([TimeSpan]::FromHours(8))
$firstRun = [DateTimeOffset]::new($chinaNow.Date.AddHours(8).AddMinutes(30), $chinaNow.Offset)
if ($firstRun -le $chinaNow) {
    $firstRun = $firstRun.AddDays(1)
}
$boundary = $firstRun.ToString("yyyy-MM-dd'T'HH:mm:sszzz")
if ($PSCmdlet.ShouldProcess($taskName, "Register under $UserId daily from $boundary")) {
    $action = New-ScheduledTaskAction -Execute $wrapperPath -WorkingDirectory $backendRoot
    $trigger = New-ScheduledTaskTrigger -Daily -At $firstRun.LocalDateTime
    $trigger.StartBoundary = $boundary
    $principal = New-ScheduledTaskPrincipal -UserId $UserId -LogonType Interactive
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew `
        -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 30) -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
    $definition = New-ScheduledTask -Action $action -Trigger $trigger -Principal $principal -Settings $settings `
        -Description 'Daily product quality report audit. Reads the share and logs missing or ambiguous reports.'
    Register-ScheduledTask -TaskName $taskName -TaskPath '\' -InputObject $definition | Out-Null

    $registered = Get-ScheduledTask -TaskName $taskName -TaskPath '\'
    if ($registered.Actions.Count -ne 1 -or $registered.Triggers.Count -ne 1 -or
        $registered.Actions[0].Execute -ne $wrapperPath -or
        $registered.Principal.LogonType -ne 'Interactive' -or
        [DateTimeOffset]::Parse($registered.Triggers[0].StartBoundary) -ne $firstRun -or
        $registered.Triggers[0].DaysInterval -ne 1) {
        throw 'Task registered, but the action or daily schedule failed read-back verification.'
    }
    [pscustomobject]@{ TaskName = $taskName; Account = $registered.Principal.UserId; FirstRun = $boundary; Action = $wrapperPath }
}
