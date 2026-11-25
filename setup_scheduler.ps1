param(
    [string]$TaskName = "ThreadsFreedomAutoposter",
    [string[]]$Times = @("10:30", "14:30", "19:00", "22:00")
)

$ErrorActionPreference = "Stop"

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonExe = "C:\Users\Huawei\AppData\Local\Python\bin\pythonw.exe"
if (-not (Test-Path $PythonExe)) {
    $PythonExe = "C:\Users\Huawei\AppData\Local\Python\bin\python.exe"
}
if (-not (Test-Path $PythonExe)) {
    throw "Python не найден по пути: $PythonExe"
}

$ScriptPath = Join-Path $ProjectDir "autoposter.py"
$Action = New-ScheduledTaskAction -Execute $PythonExe -Argument "`"$ScriptPath`" post-next" -WorkingDirectory $ProjectDir
$Triggers = foreach ($t in $Times) {
    New-ScheduledTaskTrigger -Daily -At $t
}

$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Triggers `
    -Settings $Settings `
    -Description "Автопубликация постов в Threads по очереди из posts.json" `
    -Force | Out-Null

Write-Host "Задача '$TaskName' создана! Расписание запуска: $($Times -join ', ')"
Write-Host "Проверить статус задачи: Get-ScheduledTask -TaskName '$TaskName'"
Write-Host "Удалить задачу: Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:`$false"
