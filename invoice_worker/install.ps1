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

    # Verificaciones obligatorias antes de registrar la tarea
    Write-Host "`nVerificando requisitos obligatorios..." -ForegroundColor Cyan

    # Token API
    $tokenOk = & $PythonExe -c @"
try:
    from utils.credential_store import get_workstation_token
    t = get_workstation_token()
    print('ok' if t else 'missing')
except Exception as e:
    print(f'error: {e}')
"@ 2>&1
    if ($tokenOk -ne 'ok') {
        Write-Host "ERROR: Token API no encontrado en Credential Manager (Gest2A3Eco/WorkstationToken)" -ForegroundColor Red
        Write-Host "Almacena el token primero con: python -c ``from utils.credential_store import store_workstation_token; store_workstation_token('TOKEN')``" -ForegroundColor Yellow
        exit 1
    }
    Write-Host "  [OK] Token API" -ForegroundColor Green

    # PostgreSQL
    $pgOk = & $PythonExe -c @"
try:
    from utils.credential_store import get_postgres_credentials
    c = get_postgres_credentials()
    print('ok' if c else 'missing')
except Exception as e:
    print(f'error: {e}')
"@ 2>&1
    if ($pgOk -ne 'ok') {
        Write-Host "ERROR: Credenciales PostgreSQL no encontradas en Credential Manager (Gest2A3Eco/PostgreSQL)" -ForegroundColor Red
        exit 1
    }
    Write-Host "  [OK] PostgreSQL Credential Manager" -ForegroundColor Green

    # Word COM
    try {
        $word = New-Object -ComObject Word.Application -ErrorAction Stop
        $word.Quit()
        [System.Runtime.Interopservices.Marshal]::ReleaseComObject($word) | Out-Null
        Write-Host "  [OK] Microsoft Word COM" -ForegroundColor Green
    } catch {
        Write-Host "ERROR: Microsoft Word no encontrado o COM no disponible. El worker requiere Word." -ForegroundColor Red
        exit 1
    }

    # Plantilla Word
    $templatePath = Join-Path $WorkerDir "plantillas_word\factura_emitida.docx"
    if (-not (Test-Path $templatePath)) {
        Write-Host "ERROR: Plantilla Word no encontrada: $templatePath" -ForegroundColor Red
        Write-Host "Copia la plantilla de factura antes de continuar." -ForegroundColor Yellow
        exit 1
    }
    Write-Host "  [OK] Plantilla Word" -ForegroundColor Green

    # Dry-run
    Write-Host "`nEjecutando dry-run..." -ForegroundColor Cyan
    Push-Location $WorkerDir
    & $PythonExe -m invoice_worker --dry-run
    $dryRunExit = $LASTEXITCODE
    Pop-Location
    if ($dryRunExit -ne 0) {
        Write-Host "ERROR: El dry-run fallo. Corrige los problemas antes de instalar la tarea." -ForegroundColor Red
        exit 1
    }
    Write-Host "  [OK] Dry-run exitoso" -ForegroundColor Green

    # Registrar tarea con usuario interactivo y AtLogOn
    Write-Host "`nRegistrando tarea programada..." -ForegroundColor Cyan
    $action = New-ScheduledTaskAction `
        -Execute $PythonExe `
        -Argument "-m invoice_worker" `
        -WorkingDirectory $WorkerDir

    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME

    $settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -RestartCount 3 `
        -RestartInterval (New-TimeSpan -Minutes 5) `
        -ExecutionTimeLimit (New-TimeSpan -Days 365)

    # Interactive: el usuario debe estar conectado (no S4U)
    $principal = New-ScheduledTaskPrincipal `
        -UserId $env:USERNAME `
        -LogonType Interactive `
        -RunLevel Limited

    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $action `
        -Trigger $trigger `
        -Settings $settings `
        -Principal $principal `
        -Description "Worker de facturacion online Gest2A3Eco (requiere sesion interactiva para Word COM y Credential Manager)" `
        -Force

    Write-Host "Tarea '$TaskName' registrada con LogonType=Interactive y trigger AtLogOn." -ForegroundColor Green
    Write-Host "El worker arrancara automaticamente al iniciar sesion el usuario $env:USERNAME." -ForegroundColor Green
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
