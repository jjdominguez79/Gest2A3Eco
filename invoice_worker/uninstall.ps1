# uninstall.ps1 - Desinstalacion del worker de facturacion online

param(
    [string]$TaskName = "Gest2A3Eco_InvoiceWorker"
)

$ErrorActionPreference = "Stop"

Write-Host "=== Desinstalacion del Worker de Facturacion ===" -ForegroundColor Cyan

# 1. Detener y eliminar tarea programada
$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($task) {
    if ($task.State -eq "Running") {
        Stop-ScheduledTask -TaskName $TaskName
        Write-Host "Tarea detenida." -ForegroundColor Yellow
    }
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "Tarea programada eliminada." -ForegroundColor Green
} else {
    Write-Host "No se encontro tarea programada '$TaskName'."
}

Write-Host ""
Write-Host "=== Desinstalacion completada ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "Nota: los directorios de PDFs, logs y plantillas no se han eliminado."
Write-Host "Las credenciales en Credential Manager no se han modificado."
