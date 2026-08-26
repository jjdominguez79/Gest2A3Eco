# install.ps1 - Instalacion del worker de facturacion online
# Ejecutar como administrador si se requiere registro de tarea programada
#
# Uso:
#   .\install.ps1
#   .\install.ps1 -WorkerDir "C:\Gest2A3Eco\invoice_worker"

param(
    [string]$WorkerDir = (Split-Path -Parent $PSScriptRoot),
    [string]$TaskName = "Gest2A3Eco_InvoiceWorker",
    [string]$PythonExe = ""
)

$ErrorActionPreference = "Stop"

Write-Host "=== Instalacion del Worker de Facturacion ===" -ForegroundColor Cyan
Write-Host ""

# 1. Detectar Python
if (-not $PythonExe) {
    $PythonExe = (Get-Command python -ErrorAction SilentlyContinue).Source
    if (-not $PythonExe) {
        $PythonExe = (Get-Command python3 -ErrorAction SilentlyContinue).Source
    }
}
if (-not $PythonExe -or -not (Test-Path $PythonExe)) {
    Write-Host "ERROR: Python no encontrado. Especifica -PythonExe." -ForegroundColor Red
    exit 1
}
Write-Host "Python: $PythonExe"

# 2. Verificar directorio del worker
if (-not (Test-Path "$WorkerDir\invoice_worker\worker.py")) {
    Write-Host "ERROR: No se encontro invoice_worker\worker.py en $WorkerDir" -ForegroundColor Red
    exit 1
}
Write-Host "Directorio: $WorkerDir"

# 3. Crear directorios necesarios
$dirs = @(
    "$WorkerDir\plantillas_word",
    "$WorkerDir\pdfs_generados",
    "$WorkerDir\logs"
)
foreach ($dir in $dirs) {
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
        Write-Host "Directorio creado: $dir"
    }
}

# 4. Verificar Word instalado
try {
    $word = New-Object -ComObject Word.Application -ErrorAction Stop
    $wordVersion = $word.Version
    $word.Quit()
    [System.Runtime.Interopservices.Marshal]::ReleaseComObject($word) | Out-Null
    Write-Host "Microsoft Word detectado: version $wordVersion" -ForegroundColor Green
} catch {
    Write-Host "ADVERTENCIA: Microsoft Word no detectado. El worker no podra generar PDFs." -ForegroundColor Yellow
}

# 5. Verificar credenciales en Credential Manager
Write-Host ""
Write-Host "Verificando credenciales..." -ForegroundColor Cyan

$creds = @(
    @{Name="Gest2A3Eco/WorkstationToken"; Required=$true; Desc="Token del backend"},
    @{Name="Gest2A3Eco/PostgreSQL"; Required=$false; Desc="Credenciales PostgreSQL"}
)
foreach ($cred in $creds) {
    $stored = cmdkey /list:$($cred.Name) 2>$null | Select-String "Target"
    if ($stored) {
        Write-Host "  $($cred.Desc): OK" -ForegroundColor Green
    } else {
        $level = if ($cred.Required) { "Red" } else { "Yellow" }
        $prefix = if ($cred.Required) { "FALTA" } else { "ADVERTENCIA" }
        Write-Host "  $prefix - $($cred.Desc): no encontrado en Credential Manager" -ForegroundColor $level
        if ($cred.Required) {
            Write-Host "  Almacena el token con: python -c `"from utils.credential_store import store_workstation_token; store_workstation_token('TOKEN')`"" -ForegroundColor Yellow
        }
    }
}

# 6. Verificar conexion PostgreSQL
Write-Host ""
Write-Host "Verificando PostgreSQL..." -ForegroundColor Cyan
try {
    & $PythonExe -c "from utils.credential_store import get_postgres_credentials; c=get_postgres_credentials(); print('OK' if c else 'No configurado')" 2>$null
    Write-Host "  PostgreSQL: credenciales disponibles" -ForegroundColor Green
} catch {
    Write-Host "  PostgreSQL: no se pudieron verificar las credenciales" -ForegroundColor Yellow
}

# 7. Registrar tarea programada (opcional)
Write-Host ""
$registerTask = Read-Host "Registrar como tarea programada de Windows? (s/N)"
if ($registerTask -eq "s" -or $registerTask -eq "S") {
    $action = New-ScheduledTaskAction `
        -Execute $PythonExe `
        -Argument "-m invoice_worker" `
        -WorkingDirectory $WorkerDir

    $trigger = New-ScheduledTaskTrigger -AtStartup
    $settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -RestartCount 3 `
        -RestartInterval (New-TimeSpan -Minutes 5) `
        -ExecutionTimeLimit (New-TimeSpan -Days 365)

    $principal = New-ScheduledTaskPrincipal `
        -UserId $env:USERNAME `
        -LogonType S4U `
        -RunLevel Limited

    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $action `
        -Trigger $trigger `
        -Settings $settings `
        -Principal $principal `
        -Description "Worker de facturacion online Gest2A3Eco" `
        -Force

    Write-Host "Tarea programada '$TaskName' registrada." -ForegroundColor Green
    Write-Host "Inicio automatico al arrancar el sistema." -ForegroundColor Green
}

Write-Host ""
Write-Host "=== Instalacion completada ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "Para iniciar manualmente:"
Write-Host "  cd $WorkerDir"
Write-Host "  $PythonExe -m invoice_worker"
Write-Host ""
Write-Host "Para verificar el backend:"
Write-Host "  Invoke-RestMethod -Uri `"https://tramites.gestinem.es/health`""
