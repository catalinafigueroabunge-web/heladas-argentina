Add-Type -AssemblyName System.Windows.Forms

$dir    = "C:\Users\s1134058\heladas-argentina"
$python = "$dir\.venv\Scripts\python.exe"
$script = "$dir\update_dashboard.py"
$logOut = "$dir\logs\scheduler.log"
$logErr = "$dir\logs\scheduler_err.log"

$respuesta = [System.Windows.Forms.MessageBox]::Show(
    "Actualizacion semanal del Dashboard de Heladas Argentina`n`n" +
    "Periodo: 1 ene hasta hoy - 5 dias`n" +
    "Duracion estimada: ~20 min`n`n" +
    "Deseas actualizar ahora?",
    "Dashboard Heladas — Actualizacion Semanal",
    [System.Windows.Forms.MessageBoxButtons]::YesNo,
    [System.Windows.Forms.MessageBoxIcon]::Question,
    [System.Windows.Forms.MessageBoxDefaultButton]::Button1
)

if ($respuesta -eq [System.Windows.Forms.DialogResult]::Yes) {
    [System.Windows.Forms.MessageBox]::Show(
        "Actualizacion iniciada en segundo plano.`nRevisa logs\scheduler.log para el progreso.",
        "Dashboard Heladas — Actualizando...",
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::Information
    ) | Out-Null

    New-Item -ItemType Directory -Path "$dir\logs" -Force | Out-Null

    $proc = Start-Process -FilePath $python `
        -ArgumentList "`"$script`"" `
        -WorkingDirectory $dir `
        -RedirectStandardOutput $logOut `
        -RedirectStandardError  $logErr `
        -NoNewWindow -PassThru

    $proc.WaitForExit()

    $exitMsg = if ($proc.ExitCode -eq 0) {
        "Dashboard publicado exitosamente en GitHub Pages."
    } else {
        "Hubo un error (exit code $($proc.ExitCode)). Revisa logs\scheduler_err.log"
    }

    [System.Windows.Forms.MessageBox]::Show(
        $exitMsg,
        "Dashboard Heladas — Resultado",
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::Information
    ) | Out-Null
}
