[CmdletBinding(SupportsShouldProcess = $true)]
param()

$ErrorActionPreference = 'Stop'
$taskName = 'HedeCheckInventoryProductLinksDaily'
$backendRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$wrapperPath = Join-Path $PSScriptRoot 'check_inventory_product_links_daily.cmd'
if ((Get-TimeZone).Id -ne 'China Standard Time') {
    throw 'Expected China Standard Time; no task registered.'
}
foreach ($requiredPath in @($wrapperPath, 'D:\python\python.exe', (Join-Path $backendRoot '.env'))) {
    if (-not (Test-Path -LiteralPath $requiredPath -PathType Leaf)) {
        throw "Required file is missing: $requiredPath"
    }
}
$existing = Get-ScheduledTask -TaskName $taskName -TaskPath '\' -ErrorAction SilentlyContinue
if ($null -ne $existing) {
    throw "Task $taskName already exists; inspect it before changing its configuration."
}
$firstRun = (Get-Date).Date.AddDays(1).AddMinutes(30)
$arguments = '/d /c ""' + $wrapperPath + '""'
$action = New-ScheduledTaskAction -Execute $env:ComSpec -Argument $arguments -WorkingDirectory $backendRoot
$trigger = New-ScheduledTaskTrigger -Daily -At $firstRun
$principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 20) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$definition = New-ScheduledTask -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description 'Daily read-only inventory product link audit at 00:30 China Standard Time. Does not rebind products or change prices.'
if ($PSCmdlet.ShouldProcess($taskName, "Register daily read-only check from $($firstRun.ToString('s')) +08:00")) {
    Register-ScheduledTask -TaskName $taskName -TaskPath '\' -InputObject $definition | Out-Null
    $registered = Get-ScheduledTask -TaskName $taskName -TaskPath '\'
    $info = Get-ScheduledTaskInfo -TaskName $taskName -TaskPath '\'
    if ($registered.Actions.Count -ne 1 -or $registered.Triggers.Count -ne 1 -or
        $registered.Actions[0].Arguments -ne $arguments -or
        $registered.Actions[0].WorkingDirectory -ne $backendRoot -or
        [datetime]$registered.Triggers[0].StartBoundary -ne $firstRun -or
        $registered.Triggers[0].DaysInterval -ne 1 -or
        $registered.Principal.UserId -notin @('SYSTEM', 'S-1-5-18')) {
        throw 'Task registered, but verification failed. Inspect the task before running it.'
    }
    $backupDirectory = Join-Path $backendRoot 'logs\scheduled-task-backups'
    New-Item -ItemType Directory -Path $backupDirectory -Force | Out-Null
    $xmlPath = Join-Path $backupDirectory ($taskName + '-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.xml')
    Export-ScheduledTask -TaskName $taskName -TaskPath '\' | Set-Content -LiteralPath $xmlPath -Encoding Unicode
    [pscustomobject]@{ TaskName = $taskName; NextRunTime = $info.NextRunTime; User = $registered.Principal.UserId; Action = $wrapperPath; Backup = $xmlPath }
}
