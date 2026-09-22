[CmdletBinding(SupportsShouldProcess = $true)]
param()

$ErrorActionPreference = 'Stop'
$taskName = 'HedeImportProductsDaily'
$backendRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$wrapperPath = Join-Path $PSScriptRoot 'sync_products_and_copywriting_daily.cmd'
if (-not (Test-Path -LiteralPath $wrapperPath -PathType Leaf)) {
    throw 'The new workflow wrapper is missing.'
}
$currentXml = schtasks /Query /TN $taskName /XML
if ($LASTEXITCODE -ne 0) {
    throw 'Could not read the current product archive task.'
}
[xml]$definition = $currentXml -join "`n"
$namespace = [System.Xml.XmlNamespaceManager]::new($definition.NameTable)
$namespace.AddNamespace('task', 'http://schemas.microsoft.com/windows/2004/02/mit/task')
$triggers = $definition.SelectNodes('/task:Task/task:Triggers/task:CalendarTrigger', $namespace)
$allTriggers = $definition.SelectNodes('/task:Task/task:Triggers/*', $namespace)
$commands = $definition.SelectNodes('/task:Task/task:Actions/task:Exec/task:Command', $namespace)
if ($triggers.Count -ne 1 -or $allTriggers.Count -ne 1 -or $commands.Count -ne 1) {
    throw 'Unexpected task structure; no changes made.'
}
$trigger = $triggers[0]
$boundary = $trigger.SelectSingleNode('task:StartBoundary', $namespace)
$interval = $trigger.SelectSingleNode('task:Repetition/task:Interval', $namespace)
$duration = $trigger.SelectSingleNode('task:Repetition/task:Duration', $namespace)
$days = $trigger.SelectSingleNode('task:ScheduleByDay/task:DaysInterval', $namespace)
if ($null -eq $boundary -or $null -eq $interval -or $null -eq $duration -or $null -eq $days) {
    throw 'Expected daily trigger with repetition; no changes made.'
}
$chinaNow = [DateTimeOffset]::UtcNow.ToOffset([TimeSpan]::FromHours(8))
$firstRun = $chinaNow.Date.AddDays(1).AddHours(4)
$boundary.InnerText = $firstRun.ToString('yyyy-MM-ddTHH:mm:ss') + '+08:00'
$interval.InnerText = 'PT30M'
$duration.InnerText = 'PT12H'
$days.InnerText = '1'
$commands[0].InnerText = $wrapperPath
$description = "Start $($boundary.InnerText), repeat every 30 minutes for 12 hours; action $wrapperPath"
if ($PSCmdlet.ShouldProcess($taskName, $description)) {
    $backupRoot = Join-Path $backendRoot 'logs\scheduled-task-backups'
    New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
    $backupPrefix = Join-Path $backupRoot ($taskName + '-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N'))
    $beforePath = $backupPrefix + '-before.xml'
    $afterPath = $backupPrefix + '-after.xml'
    [System.IO.File]::WriteAllText($beforePath, ($currentXml -join "`r`n"), [System.Text.Encoding]::Unicode)
    $definition.Save($afterPath)
    schtasks /Create /TN $taskName /XML $afterPath /F
    if ($LASTEXITCODE -ne 0) {
        throw "Task registration failed; original XML saved to $beforePath"
    }
    $registeredXml = schtasks /Query /TN $taskName /XML
    if ($LASTEXITCODE -ne 0) { throw 'Task updated, but read-back verification failed.' }
    [xml]$registered = $registeredXml -join "`n"
    $registeredBoundary = $registered.SelectSingleNode('/task:Task/task:Triggers/task:CalendarTrigger/task:StartBoundary', $namespace).InnerText
    $registeredCommand = $registered.SelectSingleNode('/task:Task/task:Actions/task:Exec/task:Command', $namespace).InnerText
    if ([DateTimeOffset]::Parse($registeredBoundary) -ne [DateTimeOffset]::Parse($boundary.InnerText) -or $registeredCommand -ne $wrapperPath) {
        throw 'Registered task does not match the requested configuration; review the backup.'
    }
    [pscustomobject]@{ TaskName = $taskName; FirstRun = $registeredBoundary; Interval = 'PT30M'; Duration = 'PT12H'; Action = $registeredCommand; Backup = $beforePath }
}
