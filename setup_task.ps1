# setup_task.ps1 — Registra la tarea semanal en Windows Task Scheduler
# Ejecutar UNA VEZ como administrador (o con permisos suficientes).
# Pedira la contrasena de Windows para configurar la tarea sin sesion abierta.

$projectDir = "C:\Users\s1134058\heladas-argentina"
$python     = "$projectDir\.venv\Scripts\python.exe"
$script     = "$projectDir\update_dashboard.py"
$taskName   = "Heladas-Dashboard-Update"

$action = New-ScheduledTaskAction `
    -Execute $python `
    -Argument "`"$script`"" `
    -WorkingDirectory $projectDir

$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At "07:00"

$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit  (New-TimeSpan -Hours 2) `
    -RunOnlyIfNetworkAvailable `
    -StartWhenAvailable `
    -MultipleInstances   IgnoreNew

$creds = Get-Credential -UserName $env:USERNAME `
    -Message "Ingresa tu contrasena de Windows para registrar la tarea programada"

Register-ScheduledTask `
    -TaskName    $taskName `
    -Description "Actualiza el dashboard de heladas semanalmente (Meteoblue + Open-Meteo + GitHub Pages)" `
    -Action      $action `
    -Trigger     $trigger `
    -Settings    $settings `
    -RunLevel    Highest `
    -User        $creds.UserName `
    -Password    $creds.GetNetworkCredential().Password `
    -Force

Write-Host ""
Write-Host "Tarea '$taskName' registrada. Proxima ejecucion: lunes 07:00 AM." -ForegroundColor Green
Write-Host "Para verificar: Get-ScheduledTask -TaskName '$taskName' | Get-ScheduledTaskInfo"
